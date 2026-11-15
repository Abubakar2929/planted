# OWNER: A — see PLAN.md §2
"""API-key rotation for free tiers: several team keys per provider, each with its own limits.

Keys come from the environment (.env): ``GEMINI_API_KEY``, ``GEMINI_API_KEY_2`` … ``_N`` and
``GROQ_API_KEY``, ``GROQ_API_KEY_2`` … ``_N``. Blank values and exact duplicates are ignored.
A key is only ever named by its label, ``gemini#1`` (= ``GEMINI_API_KEY``), ``gemini#2`` (=
``GEMINI_API_KEY_2``), …; key values are never printed or logged (use ``redact()`` on any error
text before writing it anywhere).

Per key (constants in gemini.py / groq.py):
- an RPM limiter (sliding 60 s window): Gemini 14, Groq 25;
- a TPM limiter for Groq (7,000 tokens / 60 s; a request reserves its estimate, corrected to the
  real usage when it finishes);
- a concurrency cap: Gemini 2, Groq 1.

``KeyPool.acquire()`` hands out keys round-robin among the keys that are neither exhausted nor
backing off and have RPM/TPM/concurrency room; it waits when none has room right now. When every
key of the provider is exhausted it raises ``QuotaExhausted``.

429 handling (``classify_429``): a **daily** quota error ("per day", "PerDay", "RPD", "TPD",
"tokens per day", "requests per day", or a retry-after above one hour) marks the key exhausted
until its reset (the retry-after when the error gives one; otherwise next midnight Pacific for
Gemini, one hour for Groq). A **per-minute** 429 backs off that key only, for the retry-after the
error gives (no key-level back-off when it gives none; the caller's own back-off applies).

Which key served a call is not part of the cache key (planted/agent/cache.py): all keys reach the
same model, so the result is the same.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

log = logging.getLogger("planted.keys")

DAY_MARKERS = ("per day", "perday", "rpd", "tpd", "tokens per day", "requests per day")
DAILY_RETRY_S = 3600.0  # a retry-after above this means a daily quota


class QuotaExhausted(RuntimeError):
    """Every key of ``provider`` hit its daily quota. ``reset_at`` = earliest reset (epoch s)."""

    def __init__(self, provider: str, reset_at: float | None = None, detail: str = ""):
        self.provider = provider
        self.reset_at = reset_at
        when = (datetime.fromtimestamp(reset_at, timezone.utc).isoformat(timespec="minutes")
                if reset_at else "unknown")
        super().__init__(f"all {provider} keys exhausted (earliest reset {when} UTC){detail}")


# --------------------------------------------------------------------------- 429 parsing
_DUR = re.compile(r"(?:retry|try again)\s+(?:in|after)\s+((?:\d+(?:\.\d+)?\s*(?:h|ms|m|s)\s*)+)", re.I)
_DELAY = re.compile(r"retry_?delay\W{0,5}(\d+(?:\.\d+)?)s", re.I)
_PART = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|h|m|s)", re.I)


def parse_retry_after(text: str, headers: dict | None = None) -> float | None:
    """Seconds to wait, from a Retry-After header or the error text; None if not stated."""
    if headers:
        for k, v in headers.items():
            if str(k).lower() == "retry-after":
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
    m = _DELAY.search(text or "")
    if m:
        return float(m.group(1))
    m = _DUR.search(text or "")
    if m:
        unit = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
        return sum(float(n) * unit[u.lower()] for n, u in _PART.findall(m.group(1)))
    return None


def classify_429(text: str, retry_after: float | None) -> str:
    """'daily' or 'minute'."""
    low = (text or "").lower()
    if any(mk in low for mk in DAY_MARKERS):
        return "daily"
    if retry_after is not None and retry_after > DAILY_RETRY_S:
        return "daily"
    return "minute"


def is_rate_limit(e: BaseException) -> bool:
    try:
        import litellm

        if isinstance(e, litellm.RateLimitError):
            return True
    except ImportError:  # pragma: no cover
        pass
    return getattr(e, "status_code", None) == 429


def error_headers(e: BaseException) -> dict | None:
    resp = getattr(e, "response", None)
    h = getattr(resp, "headers", None)
    try:
        return dict(h) if h is not None else None
    except Exception:  # noqa: BLE001
        return None


def next_pacific_midnight(now: float) -> float:
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Los_Angeles")
    except Exception:  # noqa: BLE001 - no tzdata: PST
        tz = timezone(timedelta(hours=-8))
    d = datetime.fromtimestamp(now, tz)
    nxt = (d + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.timestamp()


# --------------------------------------------------------------------------- keys
def discover_keys(env_name: str, environ: dict | None = None) -> list[tuple[int, str]]:
    """[(index, value)] for ENV, ENV_2, … ENV_N (any N, sorted), blanks and duplicates dropped."""
    environ = os.environ if environ is None else environ
    pat = re.compile(rf"^{re.escape(env_name)}(?:_(\d+))?$")
    found = []
    for k, v in environ.items():
        m = pat.match(k)
        if m and v and v.strip():
            found.append((int(m.group(1) or 1), v.strip()))
    out, seen = [], set()
    for i, v in sorted(found):
        if v not in seen:
            seen.add(v)
            out.append((i, v))
    return out


@dataclass(eq=False)
class KeySlot:
    label: str
    value: str = field(repr=False)
    rpm: int
    tpm: int | None
    concurrency: int
    in_flight: int = 0
    calls: deque = field(default_factory=deque)       # request timestamps (60 s window)
    tokens: deque = field(default_factory=deque)      # [ts, tokens] (60 s window)
    exhausted_until: float = 0.0
    backoff_until: float = 0.0
    n_ok: int = 0
    n_429_minute: int = 0
    n_429_daily: int = 0

    def __repr__(self) -> str:  # never show the value
        return f"KeySlot({self.label})"


class Lease:
    """One acquired key; hand it back with ``pool.release(lease, tokens_used)``."""

    def __init__(self, slot: KeySlot, reserved: int, entry: list | None):
        self.slot, self.reserved, self.entry = slot, reserved, entry

    @property
    def label(self) -> str:
        return self.slot.label

    @property
    def api_key(self) -> str:
        return self.slot.value


class KeyPool:
    WINDOW_S = 60.0

    def __init__(self, provider: str, keys: list[tuple[int, str]], *, rpm: int, tpm: int | None,
                 concurrency: int, daily_reset: str = "pacific_midnight",
                 clock=time.time, wait_step: float = 0.25):
        self.provider = provider
        self.slots = [KeySlot(f"{provider}#{i}", v, rpm, tpm, concurrency) for i, v in keys]
        self.daily_reset = daily_reset
        self._clock = clock
        self._wait_step = wait_step
        self._cv = threading.Condition()
        self._rr = 0

    def __len__(self) -> int:
        return len(self.slots)

    # ---- internals (call with the lock held)
    def _trim(self, s: KeySlot, now: float) -> None:
        while s.calls and now - s.calls[0] >= self.WINDOW_S:
            s.calls.popleft()
        while s.tokens and now - s.tokens[0][0] >= self.WINDOW_S:
            s.tokens.popleft()

    def _exhausted(self, s: KeySlot, now: float) -> bool:
        return s.exhausted_until > now

    def _has_room(self, s: KeySlot, now: float, est: int) -> bool:
        if self._exhausted(s, now) or s.backoff_until > now or s.in_flight >= s.concurrency:
            return False
        self._trim(s, now)
        if len(s.calls) >= s.rpm:
            return False
        if s.tpm is not None and s.tokens:
            if sum(t for _, t in s.tokens) + est > s.tpm:
                return False
        return True

    def _check_all_exhausted(self, now: float) -> None:
        if self.slots and all(self._exhausted(s, now) for s in self.slots):
            raise QuotaExhausted(self.provider, min(s.exhausted_until for s in self.slots))

    # ---- public
    def acquire(self, est_tokens: int = 0, timeout: float | None = None) -> Lease:
        """Block until some key has room; round-robin. Raises QuotaExhausted when all are spent."""
        if not self.slots:
            raise RuntimeError(f"no {self.provider} keys configured")
        deadline = None if timeout is None else self._clock() + timeout
        with self._cv:
            while True:
                now = self._clock()
                self._check_all_exhausted(now)
                n = len(self.slots)
                for j in range(n):
                    s = self.slots[(self._rr + j) % n]
                    if self._has_room(s, now, est_tokens):
                        self._rr = (self._rr + j + 1) % n
                        s.in_flight += 1
                        s.calls.append(now)
                        entry = None
                        if s.tpm is not None:
                            entry = [now, est_tokens]
                            s.tokens.append(entry)
                        return Lease(s, est_tokens, entry)
                if deadline is not None and now >= deadline:
                    raise TimeoutError(f"no {self.provider} key free within {timeout}s")
                self._cv.wait(self._wait_step)

    def release(self, lease: Lease, tokens_used: int | None = None, ok: bool = True) -> None:
        with self._cv:
            s = lease.slot
            s.in_flight = max(0, s.in_flight - 1)
            if lease.entry is not None and tokens_used is not None:
                lease.entry[1] = tokens_used
            if ok:
                s.n_ok += 1
            self._cv.notify_all()

    def mark_exhausted(self, lease_or_slot, retry_after: float | None = None) -> None:
        s = lease_or_slot.slot if isinstance(lease_or_slot, Lease) else lease_or_slot
        with self._cv:
            now = self._clock()
            if retry_after is not None:
                until = now + retry_after
            elif self.daily_reset == "pacific_midnight":
                until = next_pacific_midnight(now)
            else:
                until = now + 3600.0
            s.exhausted_until = max(s.exhausted_until, until)
            s.n_429_daily += 1
            left = sum(not self._exhausted(x, now) for x in self.slots)
            self._cv.notify_all()
        log.warning("[keys] %s daily quota exhausted until %s UTC; %d/%d %s keys left", s.label,
                    datetime.fromtimestamp(until, timezone.utc).isoformat(timespec="minutes"),
                    left, len(self.slots), self.provider)

    def back_off(self, lease_or_slot, seconds: float) -> None:
        s = lease_or_slot.slot if isinstance(lease_or_slot, Lease) else lease_or_slot
        with self._cv:
            s.backoff_until = max(s.backoff_until, self._clock() + seconds)
            s.n_429_minute += 1
            self._cv.notify_all()
        log.info("[keys] %s per-minute limit; backing off %.1fs", s.label, seconds)

    def available(self) -> int:
        now = self._clock()
        with self._cv:
            return sum(not self._exhausted(s, now) for s in self.slots)

    def status(self) -> list[dict]:
        now = self._clock()
        with self._cv:
            return [{"key": s.label, "exhausted": self._exhausted(s, now), "ok": s.n_ok,
                     "429_minute": s.n_429_minute, "429_daily": s.n_429_daily} for s in self.slots]

    def redact(self, text: str) -> str:
        for s in self.slots:
            if s.value and s.value in text:
                text = text.replace(s.value, f"<{s.label}>")
        return text


# --------------------------------------------------------------------------- registry
_pools: dict[str, KeyPool] = {}
_pools_lock = threading.Lock()


def build_pool(provider: str, environ: dict | None = None) -> KeyPool:
    from planted.providers import PROVIDERS

    mod = PROVIDERS[provider]
    return KeyPool(provider, discover_keys(mod.KEY_ENV, environ), rpm=mod.KEY_RPM, tpm=mod.KEY_TPM,
                   concurrency=mod.KEY_CONCURRENCY, daily_reset=mod.DAILY_RESET)


def get_pool(provider: str) -> KeyPool:
    """The process-wide pool for a provider, built from the environment on first use."""
    with _pools_lock:
        if provider not in _pools:
            _pools[provider] = build_pool(provider)
        return _pools[provider]


def set_pool(provider: str, pool: KeyPool | None) -> None:
    """Replace (or with None, forget) a provider's pool; used by tests and scripts."""
    with _pools_lock:
        if pool is None:
            _pools.pop(provider, None)
        else:
            _pools[provider] = pool


def key_counts() -> dict[str, int]:
    from planted.providers import PROVIDERS, _load_env

    _load_env()
    return {p: len(get_pool(p)) for p in PROVIDERS}


def redact(text: str) -> str:
    """Replace every known key value in ``text`` with its label (e.g. ``<gemini#2>``)."""
    text = str(text)
    with _pools_lock:
        pools = list(_pools.values())
    for p in pools:
        text = p.redact(text)
    for env in ("GEMINI_API_KEY", "GROQ_API_KEY"):  # keys not (yet) in a pool
        for i, v in discover_keys(env):
            if v in text:
                text = text.replace(v, f"<{env.split('_')[0].lower()}#{i}>")
    return text
