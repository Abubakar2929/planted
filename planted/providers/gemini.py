# OWNER: A — see PLAN.md §2
"""Gemini quirks (key: GEMINI_API_KEY in .env).

- Tool-call arguments can come back as a dict rather than a JSON string; the shared
  normaliser in planted.providers accepts both.
- A reply that only calls tools may have content None or ""; both become "".
"""

from __future__ import annotations

from typing import Any

PROVIDER = "gemini"
KEY_ENV = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini/gemini-3.1-flash-lite"
DEFAULT_CONCURRENCY = 8


def adjust_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Provider-specific request changes before litellm.completion (none needed yet)."""
    return kwargs
