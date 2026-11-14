# OWNER: A — see PLAN.md §2
"""Append Contract-2 LogLines to logs/*.jsonl.

Each line is validated against contracts.schemas.LogLine and written as JSON with sorted keys,
``(",", ":")`` separators, UTF-8 (no ASCII escaping) and ``\\n`` endings on every OS, then
flushed. ``ts`` changes between runs, so determinism checks compare ``without_ts()`` output.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from contracts.schemas import LogLine

LOG_DIR = Path("logs")
VOLATILE_FIELDS = ("ts",)


def serialise(line: LogLine) -> str:
    return json.dumps(
        line.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def without_ts(line: str | dict[str, Any]) -> str:
    """Canonical JSON of one log line with volatile fields dropped, for rerun comparisons."""
    d = json.loads(line) if isinstance(line, str) else dict(line)
    for f in VOLATILE_FIELDS:
        d.pop(f, None)
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class JsonlLogger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, line: LogLine | dict[str, Any]) -> None:
        """Validate (raises pydantic.ValidationError), then append one line and flush."""
        raw = line.model_dump() if isinstance(line, LogLine) else line
        text = serialise(LogLine.model_validate(raw)) + "\n"
        with self._lock, open(self.path, "a", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
