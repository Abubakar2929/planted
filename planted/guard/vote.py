# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Origin vote and data-void / contested gate (plan-v2.2 Steps 6 and 8)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Tally:
    answer: str            # normalised answer
    display: str           # answer as first written in rank order
    pages: list[int]       # result indices stating it
    origins: list[int]     # distinct cluster ids among those pages
    first_rank: int        # index of its first page

    @property
    def n_pages(self) -> int:
        return len(self.pages)

    @property
    def n_origins(self) -> int:
        return len(self.origins)

    @property
    def n_eff(self) -> float:
        """Effective count: sum over origins of 1 (origins, not pages)."""
        return float(len(self.origins))


def tally(answers_norm: list[str | None], answers_raw: list[str | None],
          cluster_ids: list[int]) -> list[Tally]:
    """Per answer: pages, independent origins. Sorted: most origins, then most pages, then rank."""
    by: dict[str, Tally] = {}
    for i, (a, raw, c) in enumerate(zip(answers_norm, answers_raw, cluster_ids)):
        if a is None:
            continue
        t = by.setdefault(a, Tally(a, raw or a, [], [], i))
        t.pages.append(i)
        if c not in t.origins:
            t.origins.append(c)
    return sorted(by.values(), key=lambda t: (-t.n_origins, -t.n_pages, t.first_rank))


def origin_vote(answers: list[str | None], cluster_ids: list[int]) -> dict[str, int]:
    """Independent origins (not pages) per answer."""
    return {t.answer: t.n_origins for t in tally(answers, answers, cluster_ids)}


def data_void(origin_counts: dict[str, int], min_origins: int = 2) -> bool:
    """True when the leading answer has fewer than min_origins independent origins."""
    return max(origin_counts.values(), default=0) < min_origins


def contested(tallies: list[Tally], margin: int = 0) -> bool:
    """True when the top two answers' origin counts differ by <= margin."""
    return len(tallies) >= 2 and tallies[0].n_origins - tallies[1].n_origins <= margin
