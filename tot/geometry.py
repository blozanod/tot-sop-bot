"""Finding the RideControl panel without being told where it is.

The panel is a grid of flat-coloured rectangles on a dark background, so it can be
located from the pixels alone: find every solid rect in a palette colour, keep the
ones that share the modal button size, then read the grid structure. Nothing here
depends on canvas size, browser zoom or letterboxing.

Naming comes from *relative* structure, never absolute pixels: the buttons split
into an upper and a lower block at the largest vertical gap, each block splits into
column clusters at the wide horizontal gaps, and the clusters are identified by
their left-to-right order. Verified against all 12 calibration frames.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .colors import PALETTE
from .errors import LayoutError

# Button aspect ratio is 75x36; allow generous slack for a scaled canvas.
_MIN_ASPECT, _MAX_ASPECT = 1.6, 2.6
_MIN_BUTTON_PX = 400


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _runs(row: np.ndarray) -> list[tuple[int, int]]:
    """Horizontal [start, end) runs of True in a boolean row."""
    if not row.any():
        return []
    d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def solid_rects(mask: np.ndarray, min_px: int = _MIN_BUTTON_PX) -> list[Rect]:
    """Connected components of a boolean mask, found by linking row runs.

    Buttons are solid rectangles, so working run-by-run rather than pixel-by-pixel
    is both exact and fast enough to run on a full canvas.
    """
    parent: dict[int, int] = {}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    prev: list[tuple[int, int, int]] = []
    boxes: dict[int, list[int]] = {}
    nxt = 0
    for y in range(mask.shape[0]):
        cur = []
        for s, e in _runs(mask[y]):
            parent[nxt] = nxt
            boxes[nxt] = [s, y, e - 1, y]
            for ps, pe, pid in prev:
                if s < pe and ps < e:  # overlaps the run above
                    union(pid, nxt)
            cur.append((s, e, nxt))
            nxt += 1
        prev = cur

    merged: dict[int, list[int]] = {}
    counts: dict[int, int] = {}
    for cid, (x0, y0, x1, y1) in boxes.items():
        r = find(cid)
        if r not in merged:
            merged[r] = [x0, y0, x1, y1]
            counts[r] = 0
        b = merged[r]
        b[0], b[1] = min(b[0], x0), min(b[1], y0)
        b[2], b[3] = max(b[2], x1), max(b[3], y1)
        counts[r] += x1 - x0 + 1

    out = []
    for r, (x0, y0, x1, y1) in merged.items():
        if counts[r] >= min_px:
            out.append(Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1))
    return out


def detect_buttons(frame: np.ndarray) -> list[Rect]:
    """Every button-shaped rect in a palette colour, filtered to the modal size."""
    cands: list[Rect] = []
    for color in PALETTE:
        mask = np.all(frame == color.value, axis=2)
        if not mask.any():
            continue
        for r in solid_rects(mask):
            if r.h and _MIN_ASPECT <= r.w / r.h <= _MAX_ASPECT:
                cands.append(r)
    if not cands:
        raise LayoutError("no palette-coloured rectangles found; is this the playing field?")

    # The panel's buttons are all one size; anything else is scenery that happened
    # to match the aspect ratio. Take the modal width and keep its cohort.
    widths = np.array([r.w for r in cands])
    modal = int(np.bincount(widths).argmax())
    tol = max(2, modal // 12)
    return [r for r in cands if abs(r.w - modal) <= tol]


def _cluster(values: list[float], gap: float) -> list[list[int]]:
    """Indices grouped where consecutive sorted values are within ``gap``."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups, cur = [], [order[0]]
    for prev, idx in zip(order, order[1:]):
        if values[idx] - values[prev] > gap:
            groups.append(cur)
            cur = []
        cur.append(idx)
    groups.append(cur)
    return groups


def _grid(rects: list[Rect], bh: int) -> list[list[Rect]]:
    """Order a cluster's rects into rows, each sorted left to right."""
    rows = _cluster([r.cy for r in rects], gap=bh * 0.6)
    return [sorted((rects[i] for i in row), key=lambda r: r.x) for row in rows]


#: Button keys per cluster, in row-major order. The panel layout is fixed, so a
#: cluster's identity follows from its position and shape.
_TV_ROOM = ["load", "unload", "entrance", "exit", "enable", "preshow"]
_ELEVATOR = ["enable", "doors", "load", "dispatch"]
_TOGGLES = ["automatic_doors", "daytime", "show_fullscreen", "ride_sfx", "tv_room_sound", "bgm"]
_STATUS = ["attraction", "track"]


@dataclass(frozen=True)
class Layout:
    """Where every control is, in frame pixels."""

    buttons: dict[str, Rect]
    counters: dict[str, Rect]
    hud: dict[str, Rect]
    button_w: int
    button_h: int

    @property
    def panel(self) -> Rect:
        xs = [r.x for r in self.buttons.values()]
        ys = [r.y for r in self.buttons.values()]
        x1 = max(r.right for r in self.buttons.values())
        y1 = max(r.bottom for r in self.buttons.values())
        return Rect(min(xs), min(ys), x1 - min(xs), y1 - min(ys))


def build_layout(frame: np.ndarray) -> Layout:
    """Locate every button, counter and HUD box in a frame.

    Raises LayoutError unless the panel is fully present and the expected shape,
    which doubles as the check for "are we on the playing field".
    """
    rects = detect_buttons(frame)
    if len(rects) != 32:
        raise LayoutError(
            f"expected 32 buttons, found {len(rects)}. The panel is partly hidden, "
            f"mid-animation, or this is not the playing field."
        )
    bw = int(np.median([r.w for r in rects]))
    bh = int(np.median([r.h for r in rects]))

    # Split into the upper block (TV rooms, toggles, status) and the lower block
    # (elevators) at the largest vertical gap.
    by_y = sorted(rects, key=lambda r: r.y)
    gaps = [(by_y[i + 1].y - by_y[i].y, i) for i in range(len(by_y) - 1)]
    _, split = max(gaps)
    upper, lower = by_y[: split + 1], by_y[split + 1 :]

    def clusters(block: list[Rect]) -> list[list[Rect]]:
        groups = _cluster([r.x for r in block], gap=bw * 1.4)
        return [sorted((block[i] for i in g), key=lambda r: r.x) for g in groups]

    up, lo = clusters(upper), clusters(lower)
    if [len(c) for c in up] != [6, 6, 6, 2] or [len(c) for c in lo] != [4, 4, 4]:
        raise LayoutError(
            f"unexpected panel shape: upper clusters {[len(c) for c in up]}, "
            f"lower {[len(c) for c in lo]}; expected [6, 6, 6, 2] and [4, 4, 4]."
        )

    buttons: dict[str, Rect] = {}
    for prefix, cluster, keys in (
        ("tv_room1", up[0], _TV_ROOM),
        ("tv_room2", up[1], _TV_ROOM),
        ("control", up[2], _TOGGLES),
        ("control", up[3], _STATUS),
        ("elevator1", lo[0], _ELEVATOR),
        ("elevator2", lo[1], _ELEVATOR),
        ("elevator3", lo[2], _ELEVATOR),
    ):
        flat = [r for row in _grid(cluster, bh) for r in row]
        if len(flat) != len(keys):
            raise LayoutError(f"{prefix}: expected {len(keys)} buttons, got {len(flat)}")
        for key, rect in zip(keys, flat):
            buttons[f"{prefix}.{key}"] = rect

    counters, hud = _find_boxes(frame, buttons, bw, bh)
    return Layout(buttons, counters, hud, bw, bh)


def _dark_boxes(frame: np.ndarray, bw: int, bh: int) -> list[Rect]:
    """Counter boxes, found by their pure-black top and bottom edges.

    The threshold has to stay below the panel background (#272727): a looser test
    makes the whole panel "dark" and the edge runs become meaningless.
    """
    dark = frame.max(axis=2) < 16
    lo_w, hi_w = int(bw * 0.45), int(bw * 1.4)
    edges: dict[int, list[tuple[int, int]]] = {}
    for y in range(dark.shape[0]):
        for s, e in _runs(dark[y]):
            if lo_w <= e - s <= hi_w:
                edges.setdefault(y, []).append((s, e))
    # A top edge can pair with the *next* box's top edge as easily as with its own
    # bottom edge, which invents a phantom box spanning the gap between two real
    # ones. Every real box shares one height, so accept in order of distance from
    # the modal height and reject anything overlapping a box already taken.
    cands: list[Rect] = []
    ys = sorted(edges)
    for yt in ys:
        for s, e in edges[yt]:
            for yb in ys:
                if not (bh * 0.55 <= yb - yt <= bh * 0.95):
                    continue
                for s2, e2 in edges[yb]:
                    if abs(s2 - s) <= 3 and abs(e2 - e) <= 3:
                        cands.append(Rect(s, yt, e - s, yb - yt + 1))

    if not cands:
        return []
    modal_h = int(np.bincount([c.h for c in cands]).argmax())
    out: list[Rect] = []
    for r in sorted((c for c in cands if abs(c.h - modal_h) <= 2), key=lambda c: c.y):
        clash = any(
            abs(r.x - o.x) < bw * 0.5 and r.y < o.bottom + 2 and o.y < r.bottom + 2 for o in out
        )
        if not clash:
            out.append(r)
    return out


#: (layout key, button prefix) for the five units that carry Waiting/Loaded boxes.
_UNIT_COUNTERS = ["tv_room1", "tv_room2", "elevator1", "elevator2", "elevator3"]


def _find_boxes(
    frame: np.ndarray, buttons: dict[str, Rect], bw: int, bh: int
) -> tuple[dict[str, Rect], dict[str, Rect]]:
    boxes = _dark_boxes(frame, bw, bh)
    panel_x0 = min(r.x for r in buttons.values())
    panel_y1 = max(r.bottom for r in buttons.values())

    counters: dict[str, Rect] = {}
    taken: set[int] = set()
    for unit in _UNIT_COUNTERS:
        cluster = [r for k, r in buttons.items() if k.startswith(f"{unit}.")]
        left = min(r.x for r in cluster)
        top, bottom = min(r.y for r in cluster), max(r.bottom for r in cluster)
        near = [
            (i, b)
            for i, b in enumerate(boxes)
            if i not in taken
            and b.right <= left
            and left - b.right < bw * 1.2
            and top - bh <= b.cy <= bottom + bh
        ]
        near.sort(key=lambda ib: ib[1].y)
        for name, (i, b) in zip(("waiting", "loaded"), near[:2]):
            counters[f"{unit}.{name}"] = b
            taken.add(i)

    # Whatever is left inside the panel belongs to RideControl, top to bottom.
    panel_x1 = max(r.right for r in buttons.values())
    rest = sorted(
        (
            b
            for i, b in enumerate(boxes)
            if i not in taken and panel_x0 <= b.x and b.right <= panel_x1 and b.bottom <= panel_y1 + bh * 2
        ),
        key=lambda b: b.y,
    )
    for name, b in zip(("front_waiting", "back_waiting", "visitor_counter"), rest):
        counters[f"control.{name}"] = b

    return counters, _find_hud(frame, panel_x0, bw, bh)


def _find_hud(frame: np.ndarray, panel_x0: int, bw: int, bh: int) -> dict[str, Rect]:
    """The Current Time and Your score boxes, which live left of the panel.

    These are solid dark plates roughly two and a half buttons wide, each holding a
    label line above the value. Unlike the counter boxes they are filled rather
    than outlined, so they are found as dark rects rather than by their edges.
    """
    # The HUD plates are filled rather than outlined, and their fill is lighter
    # than the counter-box edges, so this threshold is deliberately looser.
    dark = frame.max(axis=2) < 60
    cands = [
        r
        for r in solid_rects(dark, min_px=bw * bh)
        if r.right < panel_x0 and r.w > bw * 1.5 and bh * 0.7 <= r.h <= bh * 1.8 and 2.0 <= r.w / r.h <= 8.0
    ]
    # The value line overruns the dark plate by a pixel or two, which clips the
    # bottom dot of the clock's colon. Extend downwards; the game art below is
    # coloured rather than neutral, so it never registers as text.
    pad = max(4, bh // 4)
    grown = [
        Rect(r.x, r.y, r.w, min(r.h + pad, frame.shape[0] - r.y)) for r in sorted(cands, key=lambda r: r.y)
    ]
    return dict(zip(("clock", "score"), grown))
