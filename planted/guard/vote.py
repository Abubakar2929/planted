# OWNER: C — see PLAN.md §2
"""Origin vote and data-void gate."""

from __future__ import annotations


def origin_vote(answers: list[str], cluster_ids: list[int]) -> dict[str, int]:
    """TODO (C, PLAN.md §8): count independent origins (not pages) per answer."""
    raise NotImplementedError


def data_void(origin_counts: dict[str, int]) -> bool:
    """TODO (C, PLAN.md §8): True when the leading answer has < 2 independent origins."""
    raise NotImplementedError
