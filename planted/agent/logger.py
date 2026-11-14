# OWNER: A — see PLAN.md §2
"""Append Contract-2 LogLines to logs/*.jsonl."""

from __future__ import annotations

from pathlib import Path

from contracts.schemas import LogLine

LOG_DIR = Path("logs")


def append_log(line: LogLine, path: Path) -> None:
    """TODO (A, PLAN.md §8): append line.model_dump_json() + newline to path (under logs/)."""
    raise NotImplementedError
