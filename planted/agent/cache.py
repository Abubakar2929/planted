# OWNER: A — see PLAN.md §2
"""SQLite cache for model calls (.cache/llm.sqlite).

Key: sha256 of the canonical JSON of (model, seed, temperature, max_tokens, messages, tools),
with model aliases resolved first, so "gflite" and its full name share entries. An optional
``key_extra`` dict (e.g. ``{"prompt_style": "neutral"}``) is added to the key when given, so
runs that differ only in a run setting never share an entry; ``None`` leaves old keys unchanged.

A hit returns the stored call_model dict unchanged, including its original ``cost_usd`` and
``latency_ms``, so a rerun logs byte-identical Contract-2 lines. Money actually spent in this
process is ``Cache.spent_usd`` (misses only); hits cost $0.

On a race, the first put wins (INSERT OR IGNORE) and every caller returns the stored row,
so two threads never see different answers for one key.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from planted.providers import call_model, resolve_model

DEFAULT_PATH = Path(".cache") / "llm.sqlite"


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(
    model: str,
    seed: int,
    temperature: float,
    max_tokens: int,
    messages: list[dict],
    tools: list[dict] | None,
    key_extra: dict | None = None,
) -> str:
    payload = {
        "model": resolve_model(model),
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
        "tools": tools,
    }
    if key_extra is not None:
        payload["extra"] = key_extra
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class Cache:
    """Thread-safe: one SQLite connection per thread, WAL journal."""

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._stats_lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.spent_usd = 0.0
        self._conn().execute(
            "CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def get(self, key: str) -> dict[str, Any] | None:
        row = self._conn().execute("SELECT value FROM calls WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, response: dict[str, Any]) -> None:
        self._conn().execute(
            "INSERT OR IGNORE INTO calls (key, value) VALUES (?, ?)", (key, _canonical(response))
        )

    def _count(self, hit: bool, cost: float = 0.0) -> None:
        with self._stats_lock:
            if hit:
                self.hits += 1
            else:
                self.misses += 1
                self.spent_usd += cost


_default: Cache | None = None
_default_lock = threading.Lock()


def default_cache() -> Cache:
    global _default
    with _default_lock:
        if _default is None:
            _default = Cache()
        return _default


def call_model_cached(
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    seed: int = 0,
    temperature: float = 0,
    max_tokens: int = 400,
    cache: Cache | None = None,
    key_extra: dict | None = None,
) -> dict[str, Any]:
    """call_model through the cache. Same arguments -> identical dict, with no API call on a hit."""
    cache = cache or default_cache()
    key = cache_key(model, seed, temperature, max_tokens, messages, tools, key_extra)
    hit = cache.get(key)
    if hit is not None:
        cache._count(hit=True)
        return hit
    result = call_model(model, messages, tools, seed, temperature, max_tokens)
    cache._count(hit=False, cost=result["cost_usd"])
    cache.put(key, result)
    return cache.get(key)
