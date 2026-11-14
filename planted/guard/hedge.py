# OWNER: C — see PLAN.md §2
"""Hedge floor: the answer may never sound more certain than its sources."""

from __future__ import annotations


def hedge_floor(results: list[dict], origin_counts: dict[str, int], lang: str) -> str | None:
    """TODO (C, PLAN.md §8): minimum hedge level the final answer must carry."""
    raise NotImplementedError


def enforce(answer: str, hedge_floor: str | None, lang: str) -> str:
    """TODO (C, PLAN.md §8): rewrite/prefix answer so it carries at least hedge_floor (EN + UR)."""
    raise NotImplementedError
