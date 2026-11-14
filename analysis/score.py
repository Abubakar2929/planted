# OWNER: C — see PLAN.md §2
"""Outcome scoring: correct / flip / abstain_hedge / drift."""

from __future__ import annotations

from contracts.schemas import LogLine


def score(line: LogLine) -> str:
    """TODO (C, PLAN.md §8): classify one run into an outcome from LogLine fields only."""
    raise NotImplementedError
