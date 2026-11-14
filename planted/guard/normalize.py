# OWNER: C — see PLAN.md §2
"""Text normalisation for Guard."""

from __future__ import annotations


def normalize(text: str, lang: str) -> str:
    """TODO (C, PLAN.md §8): NFKC, strip ZWNJ/ZWJ, Urdu letter folding."""
    raise NotImplementedError


def shingles(text: str, lang: str) -> set[str]:
    """TODO (C, PLAN.md §8): shingles for MinHash; character 5-grams for Urdu."""
    raise NotImplementedError
