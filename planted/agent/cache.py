# OWNER: A — see PLAN.md §2
"""SQLite cache for model calls, keyed by sha256(model + seed + messages + tools)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(".cache") / "llm_cache.sqlite"


def cache_key(model: str, seed: int, messages: list[dict], tools: list[dict] | None) -> str:
    """TODO (A, PLAN.md §8): sha256 hex of a canonical JSON of model, seed, messages, tools."""
    raise NotImplementedError


class Cache:
    """TODO (A, PLAN.md §8): SQLite-backed get/put of model responses by cache_key()."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = path

    def get(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def put(self, key: str, response: dict[str, Any]) -> None:
        raise NotImplementedError
