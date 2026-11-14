# OWNER: A — see PLAN.md §2
"""Groq adapter (key: GROQ_API_KEY in .env)."""

from __future__ import annotations

from typing import Any

DEFAULT_MODEL = "groq/openai/gpt-oss-120b"


def complete(
    messages: list[dict], tools: list[dict] | None, seed: int, model: str = DEFAULT_MODEL
) -> dict[str, Any]:
    """TODO (A, PLAN.md §8): one seeded tool-calling completion via LiteLLM (through the cache)."""
    raise NotImplementedError
