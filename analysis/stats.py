# OWNER: C — see PLAN.md §2
"""Statistics: Wilson CIs, question-clustered logit, bootstrap k50, TOST, Holm."""

from __future__ import annotations


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """TODO (C, PLAN.md §8): Wilson score interval."""
    raise NotImplementedError


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """TODO (C, PLAN.md §8): Holm adjustment across H1, H2, H3, G1, G2, G3, G4."""
    raise NotImplementedError
