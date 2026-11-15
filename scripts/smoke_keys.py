# OWNER: A — see PLAN.md §2
"""Check every team API key, then measure Gemini throughput through the key rotation.

Usage: python scripts/smoke_keys.py [--n 20]   (reads .env)

1. Counts the keys found per provider (GEMINI_API_KEY, GEMINI_API_KEY_2 … _N; GROQ_API_KEY, …).
2. One tiny call per key (uncached, no retries); prints per key ``OK``, ``QUOTA_EXHAUSTED``,
   ``RATE_LIMITED`` (per-minute 429), ``INVALID`` (rejected key) or ``ERROR`` (anything else).
3. ``--n`` quick Gemini calls through planted.providers.call_model (round-robin over the keys that
   answered OK, per-key RPM / concurrency limits on) and the achieved requests/min.

Keys are shown only as labels such as ``gemini#2``; key values are never printed (error text is
passed through ``redact``).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if __package__ in (None, ""):  # `python scripts/smoke_keys.py` from the repo root
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planted.agent.pricing import cost_usd
from planted.providers import PROVIDERS, _load_env, resolve_model
from planted.providers import keys as K

MODELS = {"gemini": "gflite31", "groq": "gptoss"}
MESSAGES = [{"role": "user", "content": "Reply with the single word OK."}]
MAX_TOKENS = 32   # gpt-oss reasons first; a 'length' finish still proves the key works
EST_IN = 20


def status_of(e: BaseException) -> str:
    """Map a provider error to OK / QUOTA_EXHAUSTED / RATE_LIMITED / INVALID / ERROR."""
    import litellm

    text = str(e)
    if K.is_rate_limit(e):
        ra = K.parse_retry_after(text, K.error_headers(e))
        return "QUOTA_EXHAUSTED" if K.classify_429(text, ra) == "daily" else "RATE_LIMITED"
    low = text.lower()
    if (isinstance(e, (litellm.AuthenticationError, litellm.PermissionDeniedError))
            or getattr(e, "status_code", None) in (401, 403)
            or "api key not valid" in low or "api_key_invalid" in low or "invalid api key" in low):
        return "INVALID"
    return "ERROR"


def check_key(provider: str, label: str, value: str) -> tuple[str, str]:
    import litellm

    litellm.suppress_debug_info = True
    model = resolve_model(MODELS[provider])
    t0 = time.perf_counter()
    try:
        r = litellm.completion(model=model, messages=MESSAGES, max_tokens=MAX_TOKENS,
                               temperature=0, api_key=value)
    except Exception as e:  # noqa: BLE001 - classified below
        st = status_of(e)
        if st in ("QUOTA_EXHAUSTED", "RATE_LIMITED"):
            ra = K.parse_retry_after(str(e), K.error_headers(e))
            return st, f"429; retry after {'unknown' if ra is None else f'{ra / 3600:.1f} h'}"
        detail = K.redact(f"{type(e).__name__}: {e}").replace(value, f"<{label}>")
        return st, " ".join(detail.split())[:200]
    ms = int((time.perf_counter() - t0) * 1000)
    fin = r.choices[0].finish_reason
    return "OK", f"{model}; finish={fin}; {ms} ms"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=20, help="Gemini calls for the throughput test")
    args = ap.parse_args(argv)
    _load_env()

    pools = {p: K.build_pool(p) for p in PROVIDERS}
    print("keys found: " + " ".join(f"{p}={len(pool)}" for p, pool in pools.items()))
    n_calls = sum(len(p) for p in pools.values()) + args.n
    est = sum(len(pools[p]) * cost_usd(resolve_model(MODELS[p]), EST_IN, MAX_TOKENS) for p in pools)
    est += args.n * cost_usd(resolve_model(MODELS["gemini"]), EST_IN, MAX_TOKENS)
    print(f"planned: {n_calls} tiny calls, est. max ${est:.6f} at paid prices (free tiers bill $0)")

    results: dict[str, Counter] = {}
    for p, pool in pools.items():
        results[p] = Counter()
        for slot in pool.slots:
            st, detail = check_key(p, slot.label, slot.value)
            results[p][st] += 1
            print(f"  {slot.label}: {st} ({detail})")
            if st in ("QUOTA_EXHAUSTED", "INVALID", "ERROR"):
                slot.exhausted_until = float("inf")  # keep it out of the throughput test
    for p, c in results.items():
        print(f"{p}: " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))

    gem = pools["gemini"]
    live = gem.available()
    if args.n <= 0 or live == 0:
        print("throughput: not run (no working Gemini key)" if args.n > 0 else "throughput: skipped")
        return 0 if live else 1
    from planted.providers import call_model

    K.set_pool("gemini", gem)

    lat: list[int] = []

    def one(i: int):
        msgs = [{"role": "user", "content": f"Reply with the number {i}."}]
        r = call_model("gflite31", msgs, seed=0, max_tokens=8)
        lat.append(r["latency_ms"])
        return r

    workers = live * PROVIDERS["gemini"].KEY_CONCURRENCY
    t0 = time.perf_counter()
    errors = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, i) for i in range(args.n)]
        for f in futs:
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"  call failed: {K.redact(f'{type(e).__name__}: {e}').splitlines()[0][:160]}")
    dt = time.perf_counter() - t0
    st = [s for s in gem.status() if not s["exhausted"]]
    ok = args.n - errors
    lat.sort()
    print(f"throughput: {ok}/{args.n} Gemini calls OK in {dt:.1f} s over {live} keys "
          f"(workers={workers}) = {ok / dt * 60:.1f} requests/min")
    print("  per key ok/429-minute/429-daily: "
          + ", ".join(f"{s['key']}={s['ok']}/{s['429_minute']}/{s['429_daily']}" for s in st))
    if lat:
        print(f"  latency of successful calls: median {lat[len(lat) // 2]} ms, max {lat[-1]} ms")
    print(f"limit at {live} keys x {PROVIDERS['gemini'].KEY_RPM} RPM = "
          f"{live * PROVIDERS['gemini'].KEY_RPM} requests/min sustained")
    return 0


if __name__ == "__main__":
    sys.exit(main())
