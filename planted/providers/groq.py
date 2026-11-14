# OWNER: A — see PLAN.md §2
"""Groq quirks (key: GROQ_API_KEY in .env).

- gpt-oss-120b is a reasoning model: its reasoning tokens count against max_tokens and its
  reasoning text arrives separately (message.reasoning_content). Only message.content is
  returned as content. If a 400-token cap truncates too many replies
  (raw_finish_reason == "length"), consider setting reasoning_effort here and recording that choice.
"""

from __future__ import annotations

from typing import Any

PROVIDER = "groq"
KEY_ENV = "GROQ_API_KEY"
DEFAULT_MODEL = "groq/openai/gpt-oss-120b"
DEFAULT_CONCURRENCY = 4


def adjust_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Provider-specific request changes before litellm.completion (none needed yet)."""
    return kwargs
