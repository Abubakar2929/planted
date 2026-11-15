# OWNER: A — see PLAN.md §2
"""Provider adapters (Gemini, Groq) for LiteLLM: one uncached model call.

``call_model`` returns a plain dict::

    {"content": str, "tool_calls": [{"id", "name", "arguments": dict}], "tokens_in": int,
     "tokens_out": int, "latency_ms": int, "cost_usd": float, "raw_finish_reason": str | None}

- Model roster (ROSTER): gflite31 = gemini/gemini-3.1-flash-lite (default, Guard model 1),
  gptoss = groq/openai/gpt-oss-120b (Guard model 2), gptoss20 = groq/openai/gpt-oss-20b (third
  bench model). "gflite" is a synonym of gflite31. resolve_model() accepts the short alias, the
  bare id ("gpt-oss-120b"), the vendor id ("openai/gpt-oss-120b") or the LiteLLM name, in any
  case; canonical_model() maps any of them back to the short alias for episode ids and logs.
  gemini-2.5-flash-lite is retired (404 for new keys) and raises ValueError.
- Keys come from .env (python-dotenv); existing environment variables win. Several keys per
  provider (GEMINI_API_KEY, GEMINI_API_KEY_2 … _N; GROQ_API_KEY, GROQ_API_KEY_2 … _N) are rotated
  by planted/providers/keys.py: per-key RPM / TPM limiters and concurrency, round-robin over the
  keys with quota left. A daily-quota 429 marks that key exhausted and the call moves to another
  key at once; when none is left, QuotaExhausted is raised. Keys appear in logs as "gemini#2".
- Retries rate-limit (429), 5xx, timeout and connection errors with deterministic
  exponential backoff (1, 2, 4, 8, 16 s), up to MAX_TRIES attempts in total (daily-quota 429s
  that move to another key do not count as attempts).
- A provider-wide semaphore (default 64, i.e. effectively off; the per-key caps are the real
  limit) can be lowered with set_concurrency() or PLANTED_CONCURRENCY_<PROVIDER>.
- seed is sent only when LiteLLM reports the provider supports it.
- latency_ms times the successful attempt only, not backoff waits.
Use planted.agent.cache.call_model_cached in experiments; this module never caches.
"""

from __future__ import annotations

import json
import os
import threading
import time
from functools import lru_cache
from types import ModuleType
from typing import Any

from planted.agent.pricing import cost_usd
from planted.providers import gemini, groq
from planted.providers.keys import (
    QuotaExhausted, classify_429, error_headers, get_pool, is_rate_limit, parse_retry_after,
)

ROSTER = {
    "gflite31": "gemini/gemini-3.1-flash-lite",
    "gptoss": "groq/openai/gpt-oss-120b",
    "gptoss20": "groq/openai/gpt-oss-20b",
}
SYNONYMS = {"gflite": "gflite31"}
MODEL_ALIASES = {**ROSTER, **{s: ROSTER[a] for s, a in SYNONYMS.items()}}
RETIRED = {"gemini-2.5-flash-lite": "404 'no longer available to new users'; use gflite31"}
PROVIDERS: dict[str, ModuleType] = {gemini.PROVIDER: gemini, groq.PROVIDER: groq}
MAX_TRIES = 6
MAX_BACKOFF_S = 60.0

_sleep = time.sleep  # tests replace this
_semaphores: dict[str, threading.Semaphore] = {}
_sem_lock = threading.Lock()
_env_loaded = False


def _long_forms(full: str) -> list[str]:
    """``groq/openai/gpt-oss-120b`` -> itself, ``openai/gpt-oss-120b``, ``gpt-oss-120b``."""
    parts = full.split("/")
    return ["/".join(parts[i:]) for i in range(len(parts))]


_NAME_TO_ALIAS: dict[str, str] = {}
for _alias, _full in ROSTER.items():
    for _name in [_alias, *_long_forms(_full)]:
        _NAME_TO_ALIAS[_name] = _alias
for _syn, _alias in SYNONYMS.items():
    _NAME_TO_ALIAS[_syn] = _alias


def _lookup(model: str) -> str | None:
    key = model.strip().lower()
    if key.rsplit("/", 1)[-1] in RETIRED:
        raise ValueError(f"model {model!r} is retired: {RETIRED[key.rsplit('/', 1)[-1]]}")
    return _NAME_TO_ALIAS.get(key)


def resolve_model(model: str) -> str:
    """Any roster name form -> LiteLLM name. Names outside the roster pass through unchanged."""
    alias = _lookup(model)
    return ROSTER[alias] if alias else model


def canonical_model(model: str) -> str:
    """Any roster name form -> short alias (``gflite31``, ``gptoss``, ``gptoss20``).

    Raises ValueError for a model outside the roster."""
    alias = _lookup(model)
    if alias is None:
        raise ValueError(f"model {model!r} is not in the roster {list(ROSTER)}")
    return alias


def provider_of(model: str) -> str:
    provider = resolve_model(model).split("/", 1)[0]
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider for model {model!r}; expected one of {list(PROVIDERS)}")
    return provider


def set_concurrency(provider: str, n: int) -> None:
    """Cap concurrent in-flight requests to a provider. Takes effect for new calls."""
    if n < 1:
        raise ValueError("concurrency must be >= 1")
    with _sem_lock:
        _semaphores[provider] = threading.Semaphore(n)


def _semaphore(provider: str) -> threading.Semaphore:
    with _sem_lock:
        if provider not in _semaphores:
            env = os.getenv(f"PLANTED_CONCURRENCY_{provider.upper()}")
            n = int(env) if env else PROVIDERS[provider].DEFAULT_CONCURRENCY
            _semaphores[provider] = threading.Semaphore(n)
        return _semaphores[provider]


def _load_env() -> None:
    global _env_loaded
    if not _env_loaded:
        from dotenv import load_dotenv

        load_dotenv()
        _env_loaded = True


@lru_cache(maxsize=None)
def _supports_seed(model: str) -> bool:
    import litellm

    provider, bare = model.split("/", 1)
    try:
        params = litellm.get_supported_openai_params(model=bare, custom_llm_provider=provider)
    except Exception:  # noqa: BLE001 - unknown to LiteLLM: don't send seed
        return False
    return "seed" in (params or [])


def _retryable(e: Exception) -> bool:
    import litellm

    transient = (
        litellm.RateLimitError,
        litellm.InternalServerError,
        litellm.ServiceUnavailableError,
        litellm.BadGatewayError,
        litellm.Timeout,
        litellm.APIConnectionError,
    )
    if isinstance(e, transient):
        return True
    status = getattr(e, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def normalise_tool_calls(calls: Any) -> list[dict[str, Any]]:
    """OpenAI-style objects or dicts, with JSON-string or dict arguments ->
    ``[{"id", "name", "arguments": dict}]``. Unparseable arguments become ``{"_raw": str}``."""
    out = []
    for c in calls or []:
        fn = _get(c, "function") or c
        args = _get(fn, "arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": args}
        elif args is None:
            args = {}
        if not isinstance(args, dict):
            args = {"_raw": args}
        out.append({"id": _get(c, "id"), "name": _get(fn, "name"), "arguments": args})
    return out


def call_model(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    seed: int = 0,
    temperature: float = 0,
    max_tokens: int = 400,
) -> dict[str, Any]:
    import litellm

    _load_env()
    model = resolve_model(model)
    provider = provider_of(model)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    if _supports_seed(model):
        kwargs["seed"] = seed
    kwargs = PROVIDERS[provider].adjust_kwargs(kwargs)
    litellm.suppress_debug_info = True  # its help banner can echo request details

    pool = get_pool(provider)
    est_tokens = len(json.dumps(messages, ensure_ascii=False)) // 4 + max_tokens
    attempt, daily_hits = 0, 0
    while True:
        lease = pool.acquire(est_tokens) if len(pool) else None  # may raise QuotaExhausted
        if lease is not None:
            kwargs["api_key"] = lease.api_key
        try:
            with _semaphore(provider):
                t0 = time.perf_counter()
                resp = litellm.completion(**kwargs)
                latency_ms = int((time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 - filtered by _retryable
            if lease is not None:
                pool.release(lease, tokens_used=0, ok=False)
                if is_rate_limit(e):
                    text = str(e)
                    retry_after = parse_retry_after(text, error_headers(e))
                    if classify_429(text, retry_after) == "daily":
                        pool.mark_exhausted(lease, retry_after)
                        daily_hits += 1
                        if daily_hits > 4 * len(pool):
                            raise QuotaExhausted(provider, None, " (repeated daily 429s)") from None
                        continue  # another key, no attempt used; acquire raises if none is left
                    if retry_after is not None:
                        pool.back_off(lease, retry_after)
            if attempt == MAX_TRIES - 1 or not _retryable(e):
                raise
            _sleep(min(2.0**attempt, MAX_BACKOFF_S))
            attempt += 1
            continue
        if lease is not None:
            u = _get(resp, "usage")
            pool.release(lease, tokens_used=int(_get(u, "prompt_tokens") or 0)
                         + int(_get(u, "completion_tokens") or 0))
        break

    choice = resp.choices[0]
    msg = choice.message
    usage = _get(resp, "usage")
    tokens_in = int(_get(usage, "prompt_tokens") or 0)
    tokens_out = int(_get(usage, "completion_tokens") or 0)
    return {
        "content": _get(msg, "content") or "",
        "tool_calls": normalise_tool_calls(_get(msg, "tool_calls")),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd(model, tokens_in, tokens_out),
        "raw_finish_reason": _get(choice, "finish_reason"),
    }


__all__ = [
    "MODEL_ALIASES", "QuotaExhausted", "ROSTER", "call_model", "canonical_model", "normalise_tool_calls",
    "provider_of", "resolve_model", "set_concurrency",
]
