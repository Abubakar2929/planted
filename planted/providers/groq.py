# OWNER: A — see PLAN.md §2
"""Groq quirks (keys: GROQ_API_KEY, GROQ_API_KEY_2 … _N in .env; see keys.py).

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
DEFAULT_CONCURRENCY = 64   # provider-wide cap; the real limits are per key (below)

# Free tier, per key (planted/providers/keys.py): gpt-oss-120b on_demand allows 8,000 tokens/min,
# 200,000 tokens/day and 1,000 requests/day (docs/progress_A.md A5); we stay under the per-minute
# token limit and use 25 requests/min. The daily token
# limit is rolling; its 429 says when to retry (fallback: re-probe after one hour).
KEY_RPM = 25
KEY_TPM = 7000
KEY_CONCURRENCY = 1
DAILY_RESET = "one_hour"


def adjust_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Provider-specific request changes before litellm.completion (none needed yet)."""
    return kwargs
