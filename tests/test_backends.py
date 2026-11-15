# OWNER: A — see PLAN.md §2
"""Key rotation for free tiers (planted/providers/keys.py). No network: litellm is monkeypatched,
and every key below is a fake string."""

import threading
from types import SimpleNamespace as NS

import litellm
import pytest

import planted.providers as prov
from planted.agent.cache import Cache, call_model_cached, cache_key
from planted.providers import keys as K
from planted.providers.keys import KeyPool, QuotaExhausted

FAKE = [(1, "fake-key-one"), (2, "fake-key-two"), (3, "fake-key-three")]


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def pool(n=3, rpm=14, tpm=None, conc=2, clock=None, provider="gemini"):
    return KeyPool(provider, FAKE[:n], rpm=rpm, tpm=tpm, concurrency=conc,
                   clock=clock or Clock(), wait_step=0.001)


def ok_response(content="ok", pt=10, ct=2):
    return NS(choices=[NS(message=NS(content=content, tool_calls=None), finish_reason="stop")],
              usage=NS(prompt_tokens=pt, completion_tokens=ct))


@pytest.fixture
def gemini_pool(monkeypatch):
    """Install a 3-key Gemini pool for call_model; restore afterwards."""
    p = pool()
    K.set_pool("gemini", p)
    monkeypatch.setattr(prov, "_sleep", lambda s: None)
    yield p
    K.set_pool("gemini", None)


# --------------------------------------------------------------------------- discovery / parsing
def test_discover_keys_numbering_blanks_and_duplicates():
    env = {"GEMINI_API_KEY": "a", "GEMINI_API_KEY_3": "c", "GEMINI_API_KEY_2": "b",
           "GEMINI_API_KEY_4": "  ", "GEMINI_API_KEY_5": "a", "GEMINI_API_KEY_X": "z",
           "GROQ_API_KEY": "g"}
    assert K.discover_keys("GEMINI_API_KEY", env) == [(1, "a"), (2, "b"), (3, "c")]
    assert K.discover_keys("GROQ_API_KEY", env) == [(1, "g")]
    p = K.KeyPool("gemini", K.discover_keys("GEMINI_API_KEY", env), rpm=1, tpm=None, concurrency=1)
    assert [s.label for s in p.slots] == ["gemini#1", "gemini#2", "gemini#3"]
    assert repr(p.slots[0]) == "KeySlot(gemini#1)"  # repr never shows the value


@pytest.mark.parametrize("text,ra,kind", [
    ("Quota exceeded for metric generate_content_free_tier_requests, quotaId: "
     "GenerateRequestsPerDayPerProjectPerModel-FreeTier. Please retry in 21h52m3.2s", 78723.2, "daily"),
    ("Rate limit reached for model `openai/gpt-oss-120b` on tokens per day (TPD): Limit 200000. "
     "Please try again in 7m12.5s.", 432.5, "daily"),
    ("Rate limit reached on tokens per minute (TPM): Limit 8000. Please try again in 2.35s.", 2.35, "minute"),
    ('{"error": {"code": 429, "details": [{"retryDelay": "23s"}]}} PerMinute', 23.0, "minute"),
    ("RESOURCE_EXHAUSTED please retry in 2h", 7200.0, "daily"),   # > 1 hour = daily
    ("slow down", None, "minute"),
])
def test_parse_and_classify_429(text, ra, kind):
    got = K.parse_retry_after(text)
    assert got == pytest.approx(ra) if ra is not None else got is None
    assert K.classify_429(text, got) == kind


def test_retry_after_header_wins():
    assert K.parse_retry_after("try again in 5s", {"Retry-After": "12"}) == 12.0


def test_redact_replaces_key_values_with_labels():
    p = pool()
    assert p.redact("url ...?key=fake-key-two&x") == "url ...?key=<gemini#2>&x"


# --------------------------------------------------------------------------- rotation
def test_round_robin_across_keys():
    p = pool(conc=10)
    labels = []
    for _ in range(6):
        lease = p.acquire()
        labels.append(lease.label)
        p.release(lease)
    assert labels == ["gemini#1", "gemini#2", "gemini#3"] * 2


def test_rotation_skips_exhausted_keys():
    clock = Clock()
    p = pool(conc=10, clock=clock)
    p.mark_exhausted(p.slots[1], retry_after=3600 * 5)
    labels = []
    for _ in range(4):
        lease = p.acquire()
        labels.append(lease.label)
        p.release(lease)
    assert "gemini#2" not in labels and set(labels) == {"gemini#1", "gemini#3"}
    clock.t += 3600 * 5 + 1  # after its reset the key is used again
    seen = set()
    for _ in range(3):
        lease = p.acquire()
        seen.add(lease.label)
        p.release(lease)
    assert "gemini#2" in seen


def test_all_exhausted_raises_quota_exhausted():
    p = pool(n=2)
    p.mark_exhausted(p.slots[0], 100)
    p.mark_exhausted(p.slots[1], 50)
    with pytest.raises(QuotaExhausted) as ei:
        p.acquire()
    assert ei.value.provider == "gemini"
    assert ei.value.reset_at == pytest.approx(p._clock() + 50)


def test_daily_reset_without_retry_after_is_next_pacific_midnight():
    p = pool(n=1)
    p.mark_exhausted(p.slots[0])
    until = p.slots[0].exhausted_until
    assert 0 < until - p._clock() <= 25 * 3600


def test_rpm_limit_per_key_and_window():
    clock = Clock()
    p = pool(n=2, rpm=2, conc=10, clock=clock)
    for _ in range(4):
        p.release(p.acquire())
    with pytest.raises(TimeoutError):   # 2 keys x 2 RPM used up within the minute
        p.acquire(timeout=0)
    clock.t += 61
    p.release(p.acquire(timeout=0))


def test_tpm_limit_per_key_uses_real_usage():
    clock = Clock()
    p = pool(n=1, rpm=100, tpm=7000, conc=5, clock=clock, provider="groq")
    a = p.acquire(est_tokens=3000)
    b = p.acquire(est_tokens=3000)
    with pytest.raises(TimeoutError):
        p.acquire(est_tokens=3000, timeout=0)       # 9,000 > 7,000 reserved
    p.release(a, tokens_used=500)                    # real usage corrects the reservation
    p.release(p.acquire(est_tokens=3000, timeout=0))
    p.release(b)


def test_concurrency_cap_per_key():
    p = pool(n=1, conc=2)
    a, b = p.acquire(), p.acquire()
    with pytest.raises(TimeoutError):
        p.acquire(timeout=0)
    p.release(a)
    p.release(p.acquire(timeout=0))
    p.release(b)


def test_minute_backoff_affects_that_key_only():
    p = pool(n=2, conc=10)
    p.back_off(p.slots[0], 30)
    for _ in range(3):
        lease = p.acquire(timeout=0)
        assert lease.label == "gemini#2"
        p.release(lease)


# --------------------------------------------------------------------------- call_model
def test_call_model_moves_to_next_key_on_daily_429(monkeypatch, gemini_pool):
    used = []

    def fake(**kw):
        used.append(kw["api_key"])
        if kw["api_key"] == "fake-key-one":
            raise litellm.RateLimitError("GenerateRequestsPerDayPerProjectPerModel-FreeTier; retry in 20h",
                                         llm_provider="gemini", model="m")
        return ok_response()

    monkeypatch.setattr(litellm, "completion", fake)
    assert prov.call_model("gflite31", [{"role": "user", "content": "x"}])["content"] == "ok"
    assert used == ["fake-key-one", "fake-key-two"]
    assert gemini_pool.status()[0]["exhausted"] and gemini_pool.available() == 2


def test_call_model_raises_quota_exhausted_when_all_keys_spent(monkeypatch, gemini_pool):
    calls = []

    def fake(**kw):
        calls.append(kw["api_key"])
        raise litellm.RateLimitError("Quota exceeded: requests per day (RPD)", llm_provider="gemini", model="m")

    monkeypatch.setattr(litellm, "completion", fake)
    with pytest.raises(QuotaExhausted):
        prov.call_model("gflite31", [{"role": "user", "content": "x"}])
    assert sorted(calls) == sorted(v for _, v in FAKE)  # each key tried once, no extra retries


def test_cache_key_excludes_key_identity(monkeypatch, gemini_pool, tmp_path):
    """Two calls served by different keys share one cache entry; the model id is in the key."""
    served = []

    def fake(**kw):
        served.append(kw["api_key"])
        return ok_response(content=f"answer-{len(served)}")

    monkeypatch.setattr(litellm, "completion", fake)
    msgs = [{"role": "user", "content": "q"}]
    cache = Cache(tmp_path / "c.sqlite")
    r1 = call_model_cached("gflite31", msgs, cache=cache)
    gemini_pool.mark_exhausted(gemini_pool.slots[0], 3600 * 3)  # a different key would serve now
    r2 = call_model_cached("gflite31", msgs, cache=cache)
    assert r1 == r2 and len(served) == 1 and cache.hits == 1
    k = cache_key("gflite31", 0, 0, 400, msgs, None)
    assert k == cache_key("gemini/gemini-3.1-flash-lite", 0, 0, 400, msgs, None)
    assert k != cache_key("gptoss", 0, 0, 400, msgs, None)
    import inspect
    assert "api_key" not in inspect.signature(cache_key).parameters


def test_call_model_threads_spread_over_keys(monkeypatch, gemini_pool):
    seen, lock = [], threading.Lock()

    def fake(**kw):
        with lock:
            seen.append(kw["api_key"])
        return ok_response()

    monkeypatch.setattr(litellm, "completion", fake)
    ts = [threading.Thread(target=prov.call_model, args=("gflite31", [{"role": "user", "content": str(i)}]))
          for i in range(9)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(seen) == 9 and set(seen) == {v for _, v in FAKE}
