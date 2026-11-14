# OWNER: A — see PLAN.md §2
"""Check that each model answers one tiny tool call via planted.providers.call_model (uncached).

Usage: python scripts/smoke_keys.py   (reads .env; skips a provider whose key is missing)
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from planted.agent.pricing import cost_usd
from planted.providers import PROVIDERS, call_model, provider_of, resolve_model

MODELS = ["gflite", "gflite31", "gptoss"]
MAX_TOKENS = 400
EST_TOKENS_IN = 200  # rough upper bound for the prompt + tool schema below

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the web.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }
]
MESSAGES = [{"role": "user", "content": "Call the search tool with query 'hello'."}]


def main() -> int:
    load_dotenv()
    est = sum(cost_usd(resolve_model(m), EST_TOKENS_IN, MAX_TOKENS) for m in MODELS)
    print(f"planned: {len(MODELS)} calls, est. max ${est:.6f}")
    failed = False
    total = 0.0
    for alias in MODELS:
        model = resolve_model(alias)
        env = PROVIDERS[provider_of(model)].KEY_ENV
        if not os.getenv(env):
            print(f"{alias}: SKIP ({env} not set)")
            continue
        try:
            r = call_model(model, MESSAGES, tools=TOOLS, seed=0, max_tokens=MAX_TOKENS)
        except Exception as e:  # noqa: BLE001 - report any provider error as FAIL
            print(f"{alias}: FAIL ({model}; {type(e).__name__}: {str(e)[:200]})")
            failed = True
            continue
        names = [c["name"] for c in r["tool_calls"]]
        ok = "search" in names
        total += r["cost_usd"]
        print(
            f"{alias}: {'OK' if ok else 'FAIL'} ({model}; tool_calls={names}; "
            f"finish={r['raw_finish_reason']}; tokens in/out={r['tokens_in']}/{r['tokens_out']}; "
            f"cost=${r['cost_usd']:.6f}; latency={r['latency_ms']}ms)"
        )
        failed |= not ok
    print(f"total spent: ${total:.6f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
