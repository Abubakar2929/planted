# Progress: A (Harness & Ship)

## A1 done: mock search engine (Contract 1)

`planted/engine/mock_engine.py`, tests in `tests/test_engine.py`, fixtures in
`tests/fixtures/pages_engine.jsonl` (24 fictional `*.example` pages for `fx-known-001`).

### qid / url convention (B: please follow)

`Page` has no `qid` field, so the engine links a page to its question by:

1. an explicit `"qid"` key in the raw JSONL line, if present (the engine reads it before
   pydantic validation drops it); otherwise
2. the first url path segment: `https://<domain>/<qid>/<slug>`,
   e.g. `https://northfen-wire.example/q017/vbwa-anniversary`.

Pages whose qid is not in the questions file are not used; their urls are listed in
`engine.unindexed`. Duplicate urls across page files raise `ValueError`.

### Pool rules (`build_pool`, always exactly 10 pages)

- **Planted:** `planted=True`, `asserted_answer == planted_answer`, `lang == cond.lang`, plus
  `label` / `tier` when the condition sets them (`None` = any). `cond.k` of them.
- **Arm D** (`cond.source_hedge` set): `cond.n_agree` pages with `planted=False`,
  `asserted_answer == correct_answer`, `source_hedge == cond.source_hedge`; the rest are
  neutral filler (`planted=False`, `label="neutral"`, not asserting the correct answer).
- **Other arms:** the rest are honest pages (`planted=False`).
- Answers compare after strip + casefold. Within a group, pages are taken in **file order**,
  so doses nest (k=1 ⊂ k=3 ⊂ k=5).
- Positions are shuffled with `random.Random(sha256([seed, qid, arm, k, label, tier]))`.
  `hash()` is not used because it is salted per process.
- Too few pages raises `PoolError` naming the short group, the qid and the lang.

### Public API

```python
from planted.engine import MockEngine, PoolError, make_episode_id

eng = MockEngine(pages_path: str | list[str], questions_path: str)
eng.questions: dict[str, Question]; eng.pages_by_qid: dict[str, list[Page]]; eng.unindexed: list[str]
eng.build_pool(question, cond) -> list[Page]            # 10 pages, shuffled
eng.start_episode(episode_id, question, cond) -> None   # restarting an id resets it
eng.search(episode_id, query, lang) -> list[SearchResult]  # rank 1..10, url, title, snippet; query ignored but recorded
eng.open_url(episode_id, url) -> str                    # body, or "Page not found" if not in pool
eng.episode_pool(episode_id) -> list[Page]              # with hidden fields, for scoring/logging only
eng.episode_trace(episode_id) -> {"queries": [...], "opened": [...], "not_found": [...]}
make_episode_id(cond, qid) -> "A-k3-wire-T1-en-none-gflite-s0-q017"
#   None label/tier -> "na"; arm D adds "-h<hedge>-a<n_agree>" after lang
```

### Open questions

- Q for B: Can you put the qid in page urls (`https://<domain>/<qid>/<slug>`) or add a raw
  `"qid"` key to each page line? The shared `tests/fixtures/pages.jsonl` does neither, so the
  engine cannot use those pages.
- Q for B: For arms A/B/E, should the honest fill include only pages asserting the correct
  answer? At the moment any `planted=False` page counts, taken in file order, so put the
  honest pages that assert the correct answer first.
- Q for B: For arm D, does neutral filler = `label="neutral"` + not asserting the correct
  answer match what you generate? Is `k` always 0 in arm D?
- Q for B: For T3 cross-lingual pools, should planted pages be allowed in a language other than
  `cond.lang`? At the moment every page must match `cond.lang`.
- Q for all (contract): `SearchEngine.open_url(url)` in `contracts/schemas.py` takes no
  `episode_id`, but the engine needs it to scope urls to the episode's pool. The engine uses
  `open_url(episode_id, url)`. This still passes the runtime Protocol check, which looks only
  at method names. Should the contract be updated with an `[ALL]` commit?

## A2 done: providers, cache, pricing, logger

Files: `planted/providers/{__init__,gemini,groq}.py`, `planted/agent/{pricing,cache,logger}.py`,
`scripts/smoke_keys.py`, `tests/test_providers.py`, `tests/test_cache_logger.py`.

### API

```python
from planted.providers import call_model, resolve_model, set_concurrency, normalise_tool_calls
call_model(model, messages, tools=None, seed=0, temperature=0, max_tokens=400) -> dict
#   {content: str, tool_calls: [{id, name, arguments: dict}], tokens_in, tokens_out,
#    latency_ms, cost_usd, raw_finish_reason}
#   aliases: gflite -> gemini/gemini-2.5-flash-lite, gflite31 -> gemini/gemini-3.1-flash-lite,
#            gptoss -> groq/openai/gpt-oss-120b
#   retries 429 / 5xx / timeout / connection errors, 6 tries, backoff 1,2,4,8,16 s (no jitter)
#   concurrency: Gemini 8, Groq 4; set_concurrency("groq", 2) or PLANTED_CONCURRENCY_GROQ=2
#   seed sent only if LiteLLM lists it as supported (it does for all three models today)

from planted.agent.cache import call_model_cached, Cache, cache_key
call_model_cached(model, messages, tools=None, seed=0, temperature=0, max_tokens=400, cache=None)
#   .cache/llm.sqlite, key = sha256(canonical JSON of resolved model, seed, temperature,
#   max_tokens, messages, tools). Hit -> stored dict, unchanged (original cost_usd/latency_ms,
#   so rerun logs are byte-identical). Real spend this process: cache.spent_usd (misses only).

from planted.agent.pricing import PRICES, cost_usd   # $ per 1M tokens (in, out); KeyError if unknown
from planted.agent.logger import JsonlLogger, without_ts
JsonlLogger(path).write(LogLine | dict)   # validates, sorted keys, (",",":"), UTF-8, "\n", flush
without_ts(line) -> str                   # compare reruns with this (drops ts)
```

Notes:
- `tool_calls` items carry the provider's `id` beyond `name`/`arguments`. The agent loop needs it
  to send `role: tool` replies. On a cache hit the id is the stored one, so reruns stay stable.
- The Groq gpt-oss-120b price (0.15 / 0.60) is **unverified**. Check the Groq console and
  update `pricing.py` and `BUDGET.md`.
- gpt-oss-120b is a reasoning model, so its reasoning tokens count against `max_tokens=400`.
  Watch for `raw_finish_reason == "length"` in the pilot.

### Smoke check (`python scripts/smoke_keys.py`, 2026-11-14)

No `.env` was present on this machine, so nothing was called:

```
planned: 3 calls, est. max $0.001100
gflite: SKIP (GEMINI_API_KEY not set)
gflite31: SKIP (GEMINI_API_KEY not set)
gptoss: SKIP (GROQ_API_KEY not set)
total spent: $0.000000
```

TODO: rerun with keys in `.env` and paste the OK/FAIL lines here.
