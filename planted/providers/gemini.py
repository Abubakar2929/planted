# OWNER: A — see PLAN.md §2
"""Gemini quirks (keys: GEMINI_API_KEY, GEMINI_API_KEY_2 … _N in .env; see keys.py).

- Tool-call arguments can come back as a dict rather than a JSON string; the shared
  normaliser in planted.providers accepts both.
- A reply that only calls tools may have content None or ""; both become "".
"""

from __future__ import annotations

from typing import Any

PROVIDER = "gemini"
KEY_ENV = "GEMINI_API_KEY"
DEFAULT_MODEL = "gemini/gemini-3.1-flash-lite"
DEFAULT_CONCURRENCY = 64   # provider-wide cap; the real limits are per key (below)

# Free tier, per key (planted/providers/keys.py): 15 RPM and 500 requests/day for
# gemini-3.1-flash-lite; we stay one under the RPM limit. Daily quota resets at midnight Pacific.
KEY_RPM = 14
KEY_TPM = None
KEY_CONCURRENCY = 2
DAILY_RESET = "pacific_midnight"


def adjust_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Provider-specific request changes before litellm.completion (none needed yet)."""
    return kwargs
