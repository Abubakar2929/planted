# OWNER: A — see PLAN.md §2
"""Check that Gemini and Groq keys answer one tiny tool call each (via LiteLLM).

Usage: python scripts/smoke_keys.py   (reads .env; skips a provider whose key is missing)
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

PROVIDERS = [
    ("gemini", "GEMINI_API_KEY", "gemini/gemini-2.5-flash-lite"),
    ("groq", "GROQ_API_KEY", "groq/openai/gpt-oss-120b"),
]

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


def check(model: str) -> tuple[bool, str]:
    import litellm

    try:
        resp = litellm.completion(
            model=model, messages=MESSAGES, tools=TOOLS, seed=0, temperature=0, max_tokens=256
        )
    except Exception as e:  # noqa: BLE001 - report any provider error as FAIL
        return False, f"{type(e).__name__}: {e}"[:200]
    calls = resp.choices[0].message.tool_calls or []
    if not calls:
        return False, "no tool call returned"
    return True, f"tool_call={calls[0].function.name}"


def main() -> int:
    load_dotenv()
    failed = False
    for name, env, model in PROVIDERS:
        if not os.getenv(env):
            print(f"{name}: SKIP ({env} not set)")
            continue
        ok, detail = check(model)
        print(f"{name}: {'OK' if ok else 'FAIL'} ({model}; {detail})")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
