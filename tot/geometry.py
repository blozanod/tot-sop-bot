"""Finding the RideControl panel without being told where it is.

The panel is a grid of flat-coloured rectangles, so it can be located from the
pixels alone: find every solid rect in a palette colour, keep the ones that share
the modal button size, then read the grid structure. Nothing here depends on
canvas size, browser zoom or letterboxing.

This runs **once**, on one full-canvas frame. What it produces is a crop region and
a table of probe points inside it, and from then on the bot only ever screenshots
that region and reads those points — see ``tot.game``.

Naming comes from *relative* structure, never absolute pixels: the buttons split
into an upper and a lower block at the largest vertical gap, each block splits into
column clusters at the wide horizontal gaps, and the clusters are identified by
their left-to-right order. Verified against all 12 calibration frames.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .colors import pack, palette_mask
from .errors import PanelError

# Button aspect ratio is 75x36; allow generous slack for a scaled canvas.
_MIN_ASPECT, _MAX_ASPECT = 1.6, 2.6
_MIN_BUTTON_PX = 400

#: Probe grid inside each button, as fractions of its width and height. Nine
#: points across the middle 70%: the fill wins the vote even when the button's
#: black caption swallows most of a row.
_PROBE_FRACTIONS = (0.15, 0.5, 0.85)


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

    def moved(self, dx: int, dy: int) -> Rect:
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


# -- run-length primitives ----------------------------------------------------
# Every scan below works on horizontal runs pulled out of the whole frame in one
# vectorised pass. The obvious loop — one numpy call per row — is what made the
# first version of this file take a second and a half on a full canvas.


def _mask_runs(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every horizontal run of True. Returns (y, x0, x1), x1 inclusive."""
    h, w = mask.shape
    pad = np.zeros((h, w + 2), bool)
    pad[:, 1:-1] = mask
    d = np.diff(pad.view(np.int8), axis=1)
    sy, sx = np.nonzero(d == 1)
    _, ex = np.nonzero(d == -1)
    return sy, sx, ex - 1


def _color_runs(code: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, ...]:
    """Runs of one constant colour inside ``mask``. Returns (y, x0, x1, color)."""
    same = code[:, 1:] == code[:, :-1]
    start = mask.copy()
    start[:, 1:] &= ~same | ~mask[:, :-1]
    end = mask.copy()
    end[:, :-1] &= ~same | ~mask[:, 1:]
    sy, sx = np.nonzero(start)
    _, ex = np.nonzero(end)
    return sy, sx, ex, code[sy, sx]


def _components(
    y: np.ndarray, x0: np.ndarray, x1: np.ndarray, color: np.ndarray, min_px: int
) -> list[Rect]:
    """Bounding boxes of runs linked across rows, same colour, overlapping.

    Union-find over runs rather than pixels. A button's caption breaks its middle
    rows into fragments, so this cannot key off "every row is the same run" — but
    the fragments still overlap the solid rows above and below them, which is
    enough to pull the whole button into one component.
    """
    n = len(y)
    if n == 0:
        return []
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    # Runs arrive in row-major order, so a row is a contiguous slice and the runs
    # within it are already sorted by x. That makes the row-to-row link a merge.
    edges = np.flatnonzero(np.diff(y)) + 1
    bounds = np.concatenate(([0], edges, [n]))
    prev_y = prev_a = prev_b = -1
    for k in range(len(bounds) - 1):
        a, b = int(bounds[k]), int(bounds[k + 1])
        row = int(y[a])
        if prev_y == row - 1:
            i, j = prev_a, a
            while i < prev_b and j < b:
                if x1[i] < x0[j]:
                    i += 1
                elif x1[j] < x0[i]:
                    j += 1
                else:
                    if color[i] == color[j]:
                        ra, rb = find(i), find(j)
                        if ra != rb:
                            parent[rb] = ra
                    if x1[i] < x1[j]:
                        i += 1
                    else:
                        j += 1
        prev_y, prev_a, prev_b = row, a, b

    roots = np.fromiter((find(i) for i in range(n)), np.int64, n)
    _, inv = np.unique(roots, return_inverse=True)
    m = int(inv.max()) + 1
    px = np.bincount(inv, weights=x1 - x0 + 1, minlength=m)
    lo_x = np.full(m, 1 << 30, np.int64)
    hi_x = np.zeros(m, np.int64)
    lo_y = np.full(m, 1 << 30, np.int64)
    hi_y = np.zeros(m, np.int64)
    np.minimum.at(lo_x, inv, x0)
    np.maximum.at(hi_x, inv, x1)
    np.minimum.at(lo_y, inv, y)
    np.maximum.at(hi_y, inv, y)

    keep = px >= min_px
    return [
        Rect(int(lo_x[i]), int(lo_y[i]), int(hi_x[i] - lo_x[i] + 1), int(hi_y[i] - lo_y[i] + 1))
        for i in np.flatnonzero(keep)
    ]


def solid_rects(mask: np.ndarray, min_px: int = _MIN_BUTTON_PX) -> list[Rect]:
    """Connected components of a boolean mask."""
    y, x0, x1 = _mask_runs(mask)
    return _components(y, x0, x1, np.zeros(len(y), np.int64), min_px)


def detect_buttons(frame: np.ndarray) -> list[Rect]:
    """Every button-shaped rect in a palette colour, filtered to the modal size."""
    code = pack(frame)
    y, x0, x1, color = _color_runs(code, palette_mask(code))
    cands = [
        r
        for r in _components(y, x0, x1, color, _MIN_BUTTON_PX)
        if r.h and _MIN_ASPECT <= r.w / r.h <= _MAX_ASPECT
    ]
    if not cands:
        raise PanelError("no palette-coloured rectangles found; is this the playing field?")

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


def _grid(rects: list[Rect], bh: int) -> list[Rect]:
    """A cluster's rects in row-major order."""
    rows = _cluster([r.cy for r in rects], gap=bh * 0.6)
    return [r for row in rows for r in sorted((rects[i] for i in row), key=lambda r: r.x)]


#: Button keys per cluster, in row-major order. The panel layout is fixed, so a
#: cluster's identity follows from its position and shape.
_TV_ROOM = ["load", "unload", "entrance", "exit", "enable", "preshow"]
_ELEVATOR = ["enable", "doors", "load", "dispatch"]
_TOGGLES = ["automatic_doors", "daytime", "show_fullscreen", "ride_sfx", "tv_room_sound", "bgm"]
_STATUS = ["attraction", "track"]

#: The five units that carry Waiting/Loaded boxes.
_UNIT_COUNTERS = ["tv_room1", "tv_room2", "elevator1", "elevator2", "elevator3"]


@dataclass(frozen=True)
class Layout:
    """Where every control is, and the probe points that read them.

    ``region`` is the rect these coordinates live in — the crop the bot screenshots
    from here on. ``keys``/``probe_y``/``probe_x`` are the button table flattened
    for one vectorised read per frame.
    """

    buttons: dict[str, Rect]
    counters: dict[str, Rect]
    region: Rect
    keys: tuple[str, ...]
    probe_y: np.ndarray
    probe_x: np.ndarray
    button_w: int
    button_h: int


def build_layout(frame: np.ndarray, pad: int = 4) -> Layout:
    """Locate every button and counter in a frame.

    Raises ``PanelError`` unless the panel is fully present and the expected shape,
    which doubles as the check for "has the game started yet".
    """
    rects = detect_buttons(frame)
    if len(rects) != 32:
        raise PanelError(
            f"expected 32 buttons, found {len(rects)}. The panel is partly hidden, "
            f"mid-animation, or this is not the playing field."
        )
    bw = int(np.median([r.w for r in rects]))
    bh = int(np.median([r.h for r in rects]))

    # Split into the upper block (TV rooms, toggles, status) and the lower block
    # (elevators) at the largest vertical gap.
    by_y = sorted(rects, key=lambda r: r.y)
    _, split = max((by_y[i + 1].y - by_y[i].y, i) for i in range(len(by_y) - 1))
    upper, lower = by_y[: split + 1], by_y[split + 1 :]

    def clusters(block: list[Rect]) -> list[list[Rect]]:
        groups = _cluster([r.x for r in block], gap=bw * 1.4)
        return [sorted((block[i] for i in g), key=lambda r: r.x) for g in groups]

    up, lo = clusters(upper), clusters(lower)
    if [len(c) for c in up] != [6, 6, 6, 2] or [len(c) for c in lo] != [4, 4, 4]:
        raise PanelError(
            f"unexpected panel shape: upper clusters {[len(c) for c in up]}, "
            f"lower {[len(c) for c in lo]}; expected [6, 6, 6, 2] and [4, 4, 4]."
        )

    buttons: dict[str, Rect] = {}
    for prefix, cluster, names in (
        ("tv_room1", up[0], _TV_ROOM),
        ("tv_room2", up[1], _TV_ROOM),
        ("control", up[2], _TOGGLES),
        ("control", up[3], _STATUS),
        ("elevator1", lo[0], _ELEVATOR),
        ("elevator2", lo[1], _ELEVATOR),
        ("elevator3", lo[2], _ELEVATOR),
    ):
        flat = _grid(cluster, bh)
        if len(flat) != len(names):
            raise PanelError(f"{prefix}: expected {len(names)} buttons, got {len(flat)}")
        for name, rect in zip(names, flat):
            buttons[f"{prefix}.{name}"] = rect

    counters = _find_counters(frame, buttons, bw, bh)

    # Crop to the panel plus its counter boxes. Everything left of here — the ride
    # diagram, the clock, the score — is pixels the bot has no use for.
    boxes = list(buttons.values()) + list(counters.values())
    x0 = max(0, min(r.x for r in boxes) - pad)
    y0 = max(0, min(r.y for r in boxes) - pad)
    x1 = min(frame.shape[1], max(r.right for r in boxes) + pad)
    y1 = min(frame.shape[0], max(r.bottom for r in boxes) + pad)
    region = Rect(x0, y0, x1 - x0, y1 - y0)

    buttons = {k: r.moved(-x0, -y0) for k, r in buttons.items()}
    counters = {k: r.moved(-x0, -y0) for k, r in counters.items()}
    keys = tuple(buttons)
    probe_y, probe_x = _probes([buttons[k] for k in keys])
    return Layout(buttons, counters, region, keys, probe_y, probe_x, bw, bh)


def _probes(rects: list[Rect]) -> tuple[np.ndarray, np.ndarray]:
    """A (N, 9) grid of probe points inside each rect."""
    ys, xs = [], []
    for r in rects:
        rows = [r.y + int(r.h * f) for f in _PROBE_FRACTIONS]
        cols = [r.x + int(r.w * f) for f in _PROBE_FRACTIONS]
        ys.append([yy for yy in rows for _ in cols])
        xs.append([xx for _ in rows for xx in cols])
    return np.array(ys, np.intp), np.array(xs, np.intp)


def _dark_boxes(frame: np.ndarray, bw: int, bh: int) -> list[Rect]:
    """Counter boxes, found by their pure-black top and bottom edges.

    The threshold has to stay below the panel background (#272727): a looser test
    makes the whole panel "dark" and the edge runs become meaningless.
    """
    y, x0, x1 = _mask_runs(frame.max(axis=2) < 16)
    width = x1 - x0
    keep = (width >= int(bw * 0.45)) & (width <= int(bw * 1.4))
    edges: dict[int, list[tuple[int, int]]] = {}
    for yy, a, b in zip(y[keep].tolist(), x0[keep].tolist(), x1[keep].tolist()):
        edges.setdefault(yy, []).append((a, b))

    # A top edge can pair with the *next* box's top edge as easily as with its own
    # bottom edge, which invents a phantom box spanning the gap between two real
    # ones. Every real box shares one height, so accept in order of distance from
    # the modal height and reject anything overlapping a box already taken.
    cands: list[Rect] = []
    ys = sorted(edges)
    for yt in ys:
        for a, b in edges[yt]:
            for yb in ys:
                if not (bh * 0.55 <= yb - yt <= bh * 0.95):
                    continue
                for a2, b2 in edges[yb]:
                    if abs(a2 - a) <= 3 and abs(b2 - b) <= 3:
                        cands.append(Rect(a, yt, b - a, yb - yt + 1))
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


def _find_counters(
    frame: np.ndarray, buttons: dict[str, Rect], bw: int, bh: int
) -> dict[str, Rect]:
    panel_x0 = min(r.x for r in buttons.values())
    panel_x1 = max(r.right for r in buttons.values())
    panel_y0 = min(r.y for r in buttons.values())
    panel_y1 = max(r.bottom for r in buttons.values())

    # Scan for dark boxes only where one could possibly belong to the panel: a
    # unit's boxes sit within about 2.6 button widths to its left, and the
    # RideControl ones sit inside the panel. On a full window the rest of the
    # frame is ride artwork, which throws off tens of thousands of dark
    # rectangles and turns the overlap check below into the slowest thing here.
    sx = max(0, panel_x0 - int(bw * 3))
    sy = max(0, panel_y0 - int(bh * 2))
    ey = min(frame.shape[0], panel_y1 + int(bh * 3))
    boxes = [
        b.moved(sx, sy)
        for b in _dark_boxes(frame[sy:ey, sx:panel_x1], bw, bh)
    ]

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
    rest = sorted(
        (
            b
            for i, b in enumerate(boxes)
            if i not in taken
            and panel_x0 <= b.x
            and b.right <= panel_x1
            and b.bottom <= panel_y1 + bh * 2
        ),
        key=lambda b: b.y,
    )
    for name, b in zip(("front_waiting", "back_waiting", "visitor_counter"), rest):
        counters[f"control.{name}"] = b
    return counters
