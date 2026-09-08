"""The run record.

Two streams to one JSONL file: every action with the state it was taken in, and an
event whenever any observable changes. Together they are the causal record an SOP
step is made of — "Unload turned orange, and 1.4s later it was pressed" — and idle
frames write nothing, so a long run stays small.

Actions also carry ``cue_age_s``: how long the button had been sitting in its
current state before it was clicked. That is the number that says whether a step
is humanly achievable.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class Trace:
    """Append-only JSONL writer. ``path=None`` disables recording entirely."""

    def __init__(self, path: str | Path | None = "logs/run.jsonl"):
        self.path = Path(path) if path else None
        self._fh = None
        self.t0 = time.monotonic()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", encoding="utf-8")

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def write(self, kind: str, **fields: Any) -> None:
        if self._fh is None:
            return
        rec = {"t": round(self.elapsed, 3), "kind": kind, **fields}
        self._fh.write(json.dumps(rec, default=str) + "\n")
        self._fh.flush()

    def state_change(self, key: str, old: Any, new: Any, gloss: str, clock: str | None) -> None:
        self.write(
            "state_change",
            key=key,
            **{"from": getattr(old, "name", old), "to": getattr(new, "name", new)},
            gloss=gloss,
            clock=clock,
        )

    def action(
        self,
        key: str,
        screen_name: str,
        state: Any,
        gloss: str,
        cue_age_s: float | None,
        clock: str | None,
    ) -> None:
        self.write(
            "action",
            key=key,
            button=screen_name,
            state_when_clicked=getattr(state, "name", state),
            gloss=gloss,
            cue_age_s=None if cue_age_s is None else round(cue_age_s, 3),
            clock=clock,
        )

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
