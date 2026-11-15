# OWNER: A — see PLAN.md §2
"""Model prices in US$ per 1M tokens (input, output), keyed by full LiteLLM model name."""

from __future__ import annotations

PRICES: dict[str, tuple[float, float]] = {
    # Retired from the roster (404 for new keys); kept so old logs can still be priced.
    "gemini/gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini/gemini-3.1-flash-lite": (0.25, 1.50),
    # UNVERIFIED: check the Groq console price for gpt-oss-120b, update here and BUDGET.md.
    "groq/openai/gpt-oss-120b": (0.15, 0.60),
    # UNVERIFIED: groq.com/pricing returned no price table on 2026-11-15; this is the last
    # known Groq list price for gpt-oss-20b. Check the console, update here and BUDGET.md.
    "groq/openai/gpt-oss-20b": (0.075, 0.30),
}


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Dollar cost of one call. Raises KeyError for a model with no listed price."""
    if model not in PRICES:
        raise KeyError(f"no price for model {model!r}; add it to planted/agent/pricing.py")
    p_in, p_out = PRICES[model]
    return (tokens_in * p_in + tokens_out * p_out) / 1_000_000
