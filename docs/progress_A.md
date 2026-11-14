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
