# OWNER: C — see PLAN.md §2
"""guard(query, results, lang) public API; equals apply_defense("guard", ...)."""

from __future__ import annotations

from contracts.schemas import GuardResult


def guard(query: str, results: list[dict], lang: str = "en") -> GuardResult:
    """TODO (C, PLAN.md §8): one batched extraction call per query; normalise; build
    provenance + MinHash + answer-masked embedding edges; cluster into origins; reweight
    (never delete); data-void gate (< 2 origins); hedge floor.
    Thresholds tuned on split == "dev" only, frozen at tag prereg-v2."""
    raise NotImplementedError
