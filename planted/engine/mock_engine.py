# OWNER: A — see PLAN.md §2
"""Deterministic, seeded mock search engine implementing contracts.schemas.SearchEngine."""

from __future__ import annotations

from contracts.schemas import Page, SearchResult


class MockEngine:
    """TODO (A, PLAN.md §8): serve B's pages for an episode, deterministic and seeded.

    - search() returns rank, url, title, snippet only (never planted/label/campaign fields).
    - open_url() returns the page body.
    - Same (episode_id, query, lang, seed) must give byte-identical results.
    """

    def __init__(self, pages: list[Page], seed: int) -> None:
        self.pages = pages
        self.seed = seed

    def search(self, episode_id: str, query: str, lang: str) -> list[SearchResult]:
        raise NotImplementedError

    def open_url(self, url: str) -> str:
        raise NotImplementedError
