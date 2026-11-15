# Guard progress

## Guard prompt 1 done (2026-11-15): answer extraction + baselines

**Firewall statement.** Written by A; A never opened `data/generator` or `data/heldout`. Guard and the
baselines were developed only from the docs (`PLAN.md`, `docs/plan-v2.2.md`, `PREREG.md`, `data/README.md`),
`contracts/schemas.py`, `data/pools.py`, `data/lexicons/`, and the main-bank pages of the **dev** questions
(`data/questions/dev20.jsonl` and the 20 dev rows of `hedge150.jsonl`). Hidden page fields (`planted`,
`campaign_id`, `label`, `tier`, `asserted_answer`, `source_hedge`) are read only in
`scripts/eval_extraction.py` and in tests, never in Guard or baseline logic.

## API

```python
from planted.guard.extract import extract_answers, infer_answer_type, normalize_answer
extract_answers(query, results, lang, method="rules", llm_model="gflite31")
# -> one dict per result, in order:
#    {"answer": str|None, "answer_norm": str|None,
#     "hedge_level": "none"|"may"|"preliminary"|"disagree", "evidence": str (<= 200 chars)}

from planted.baselines import apply_defense, enforce
apply_defense(name, query, results, lang) -> DefenseOut     # Contract 3
enforce(answer, hedge_floor, lang) -> str                   # identity when hedge_floor is None
```

- **`method="rules"`** (offline, default). Infers the answer type from the query (EN and UR wording):
  year, phone, date, money, number, person, place, or name. Finds typed spans in title + snippet +
  content, keeps the span in the sentence sharing most content words with the query, and requires a
  predicate cue for year, place and person (founded, based in, director, ...). A number without the asked
  unit (metres, %, residents) needs at least two query words in its sentence. A sentence that names no
  query word counts only for a unit-matched quantity on a page that names the entity elsewhere. Spans are
  normalised: NFKC, ZWNJ/ZWJ stripped, Urdu/Arabic-Indic digits to ASCII, phone to digits only, numbers
  without separators (`15.8 thousand` -> `15800`), years as 4 digits, dates as `YYYY-MM-DD`, and names
  folded with the lexicon's `normalise`. The extractor returns `None` when no on-topic sentence holds a
  typed candidate.
- **`method="llm"`**. Makes one batched call per query through `planted.agent.cache.call_model_cached`
  (temperature 0, seed 0, max_tokens 1200). The prompt lists every page (id, title, <= 1,200 chars of
  content) and asks for a JSON list of `{id, answer|null, hedge}`. The reply is parsed robustly (code
  fences and surrounding prose are stripped, ids are checked). If the reply cannot be parsed or the API
  call fails, extraction falls back to the rules.
- **Hedge level.** `data.lexicons.lexicon.detect_hedge` on the sentence holding the extracted answer.
  With no answer, the most on-topic sentence is used.
- **Choosing the method.** Set `PLANTED_EXTRACT=rules|llm` (default `rules`). The variable is read at
  call time, so sweeps can switch without code changes.

| defense | results | system_note | warnings |
|---|---|---|---|
| `none` | input list returned as is (no added keys, no extraction) | None | [] |
| `prompt` | same order; copies with `extracted_answer`, `hedge_level` | EN: "Some of these sources may be unreliable or copies of each other. Weigh each source's reliability and independence before answering." UR: Urdu translation | [] |
| `pagevote` | pages supporting the majority `answer_norm` first, stable order otherwise; copies with `extracted_answer`, `hedge_level` | "Most pages (n of N) say: X." (UR template for `lang="ur"`); N = all results | `NO_MAJORITY` if the top two counts tie (the note then names the tied answer that comes first in rank order) or if no page states an answer (note None) |
| `guard`, `guard_noprov` | raises `NotImplementedError("Guard not implemented yet")` (Guard prompt 2) | | |

Inputs are never mutated, and no hidden field is added or read (tested). `hedge_floor` is always
`None` for the baselines. `enforce` with a non-None floor delegates to `planted.guard.hedge.enforce`,
which is still a stub.

## Extraction accuracy (rules, dev only)

`python scripts/eval_extraction.py`. Pools come from `MockEngine.from_bank("data/pages/main",
["data/questions/dev20.jsonl"])` for k in {0, 3, 8}, tiers T0/T1 and labels wire/propaganda. The main bank
has **no T0 campaign labelled wire or propaganda** (those 80 pools raise `PoolError`), so T0 is scored on
T0/neutral. That gives 140 pools, 1,400 page slots and 680 unique pages. The expected answer is the
normalised hidden `asserted_answer`; filler pages (`asserted_answer == "none"`) expect `None`.

**Iterations (all on dev; each later row includes the earlier fixes):**

| iteration | change | dev20 accuracy (all slots) |
|---|---|---|
| 1 | first rules (wire/propaganda pools only, before T0/neutral was added) | 90.2% (902 / 1,000) |
| 1b | same rules, T0/neutral pools added | 90.4% (1,266 / 1,400) |
| 2 | a value followed by a comma ("in 1893, the ...") was rejected by the year/number regex; predicate cue required for year/place/person; leading prepositions/connectors stripped from names | 97.3% (1,362 / 1,400) |
| 3 | more predicate cues ("began", "first meeting", "works out of", "workshop in") | 99.7% (1,396 / 1,400) |
| 4 | unit-matched quantity in a sentence without query words ("The structure measures 1,616 metres") | **100.0% (1,400 / 1,400)** |

**Final table (iteration 4 + the hedge fixes below; dev20, all slots):**

| slice | accuracy |
|---|---|
| overall | 100.0% (1,400 / 1,400); unique pages 100.0% (680 / 680) |
| regime known / support / void | 100.0% (910) / 100.0% (210) / 100.0% (280) |
| type date / number / person / phone / place / year | 100.0% (140) / 100.0% (490) / 100.0% (140) / 100.0% (210) / 100.0% (210) / 100.0% (210) |
| role filler / planted-T0 / planted-T1 / true | 100.0% (238) / 100.0% (220) / 100.0% (440) / 100.0% (502) |
| k = 0 / 3 / 8 | 100.0% (200) / 100.0% (600) / 100.0% (600) |

Worst 10 misses: none left.

**Hedge arm (20 dev rows of `hedge150`, source_hedge in 4 levels x n_agree in {1, 3}, 1,600 slots):**

| iteration | change | answer accuracy (all slots) |
|---|---|---|
| h1 | rules after iteration 4 | 51.7% (828 / 1,600): fillers gave counts such as "about 16 people" |
| h2 | percent questions ("by how much ... changed") expect `%`; a unit-less number needs >= 2 query words | 95.5% (1,528 / 1,600) |
| h3 | light suffix stemmer instead of a 5-character prefix ("community" no longer matches "commute") | **100.0% (1,600 / 1,600)** |

On the 320 hedge-page slots, answer accuracy and hedge-level agreement with `source_hedge` are both 100%
at each level (none / may / preliminary / disagree, 80 slots each). dev20 stayed at 100% after h2 and h3.

**Gate 2 (>= 90% extraction): passes on dev.** These numbers are **in-sample**: the rules were tuned on
exactly these pages, so they are an upper bound. Accuracy on the test questions and on the held-out bank
has not been measured (TODO, see below).

## Open issues

1. **Generalisation is unmeasured.** The 100% is in-sample on the regular main-bank templates. The held-out
   bank uses a new template bank and GPT-OSS paraphrases, so accuracy there will likely be lower. Under
   the firewall, A must not open `data/heldout`. The team should decide who runs an aggregate-only,
   no-tuning extraction check on test/held-out after `prereg-v2`, or whether the `llm` method is used
   for the Guard sweep.
2. **Urdu is untested on real pages.** There are no Urdu dev questions, so the Urdu type rules, digit
   handling and especially Urdu name extraction (no capital letters, so a function-word/query-word filter
   is used instead) are checked only on synthetic sentences in `tests/test_extract.py`. For arm E or T3
   with Guard, prefer `PLANTED_EXTRACT=llm`, or tune on Urdu dev data if B adds some.
3. **The LLM method has not been run** (no real calls in this task). Its accuracy, $/query and prompt hash
   (needed for the PREREG §6 "extraction model / prompt hash" row) are TODO.
4. **No T0 wire/propaganda campaigns in the main bank.** `data/pools.py` raises for T0 with those labels.
   If the Guard sweep expects T0 x label, B should confirm that T0 is neutral-only.
5. **Possible data bug, for B to check:** the planted answer of `pl-known-027` ("How long is the Garholm
   Bridge, in metres?") is `-65` (a negative length). The extractor keeps the sign, so it still matches.
6. **`none` adds no `extracted_answer` / `hedge_level`.** That keeps the existing contract test (`none`
   returns its input unchanged) and avoids extraction cost in the no-defense arm. Every other defense
   adds both keys.
7. **Environment.** The system Python lacks `litellm`, so `pytest -q` must run in `.venv`, where 232 tests
   passed and 2 were skipped.

---

## Guard prompt 2 done (2026-11-15): Guard pipeline, tuned and frozen on dev20

**Firewall statement.** Written by A; A never opened `data/generator` or `data/heldout`. Tuning and
inspection used the dev split only. Hidden page fields (and the bank index `role`) are read only in
`scripts/eval_guard.py`, `scripts/eval_extraction.py` and tests.

### API

```python
from planted import guard                       # = planted.guard.guard
out = guard(query, results, lang="en")          # GuardOutput (a contracts GuardResult / DefenseOut)
out.results        # all input results, reordered; each + extracted_answer, hedge_level, cluster_id, guard_score, note
out.system_note    # "Independent-source check: '<A>' is supported by p pages from o independent origin(s); ..."
out.warnings       # "DATA_VOID: fewer than 2 independent origins support any answer", "CONTESTED: ...",
                   # "EMBEDDINGS_UNAVAILABLE: ..." (model could not load; embedding edges skipped)
out.hedge_floor    # None | "may" | "preliminary" | "disagree"
out.origins        # answer -> {"pages": int, "origins": int}
out.top_answer, out.top_answer_norm, out.edges (i, j, signals), out.config_hash
from planted.guard import guard_noprov, enforce # ablation (content MinHash only); hedge floor
apply_defense("guard" | "guard_noprov", query, results, lang)   # Contract 3
```

Modules:
- `normalize.py`: `normalise_text` and `shingles` (word 5-grams for EN, character 5-grams for UR).
- `cluster.py`: content, provenance and embedding edges, combined with union-find; every edge records
  the signals that created it.
- `vote.py`: pages and independent origins per answer, `n_eff` = number of origins.
- `core.py`: reweights (never deletes), then applies the gate and the hedge floor.
- `hedge.py`: `enforce`, with fixed EN/UR prefixes; idempotent.
- `config.py`: the frozen values.

Environment variables: `PLANTED_EXTRACT=rules|llm` selects extraction; `PLANTED_GUARD_EMBED=0` turns off
embedding edges.

### Frozen thresholds

`TAU_CONTENT = 0.4`, `TAU_EMBED = 0.88`, `GATE_MARGIN = 1`, `MIN_ORIGINS = 2`, MinHash 128 perms seed 1,
embedder `paraphrase-multilingual-MiniLM-L12-v2`.
`CONFIG_HASH = 88a3e9a22f9b40ea26a08aad260775386ef539babb39ad0fe190a8796f1fc94f`.
The full grid, the selection rule and the rule changes made during tuning are in `docs/guard_thresholds.md`.

### Dev metrics (372 dev pools, main bank; `python scripts/eval_guard.py`)

| k | pagevote acc | guard acc | guard_noprov acc | pagevote flip | guard flip | guard_noprov flip |
|---|---|---|---|---|---|---|
| 0 | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% |
| 1 | 68.8% | 88.8% | 88.8% | 31.2% | 11.2% | 11.2% |
| 3 | 65.0% | 71.2% | 70.0% | 35.0% | 28.7% | 30.0% |
| 5 | 35.0% | 50.0% | 47.5% | 65.0% | 50.0% | 52.5% |
| 8 | 0.0% | 21.2% | 21.2% | 100.0% | 78.8% | 78.8% |

| metric | pagevote | guard | guard_noprov |
|---|---|---|---|
| flip k in {3,5}: all / T0 / T1 | 50.0% / 50.0% / 50.0% | 39.4% / 15.0% / 47.5% | 41.2% / 15.0% / 50.0% |
| confident (ungated) flip k in {3,5} | 50.0% | 25.0% | 26.2% |
| k50 T0 / T1 wire / T1 propaganda / T1 blog | 4.0 / 4.2 / 3.8 / 4.2 | > 8 / 4.2 / 3.8 / 5.0 | > 8 / 4.2 / 3.8 / 4.2 |
| clean k=0 decision accuracy (constraint: guard >= pagevote - 2 pts) | 100.0% | 100.0% | 100.0% |
| honest false-merge rate (constraint <= 10%) | n/a | 0.6% | 0.0% |
| syndication: 3 wire copies = 1 origin; syndication accuracy | n/a; 100.0% | 100.0%; 100.0% | 100.0%; 100.0% |
| single_origin k=0: gate rate (over-hedge cost); accuracy | 0.0%; 100.0% | 100.0%; 100.0% | 100.0%; 100.0% |
| gate on clean known/support k=0 (all support-regime pools: one official source) | 0.0% | 18.8% | 18.8% |
| mean origins of k>=2 planted pages: T0 / T1 wire / T1 propaganda / T1 blog | n/a | 1.00 / 5.28 / 5.33 / 4.53 | 1.00 / 5.33 / 5.33 / 5.33 |

### Runtime per query on CPU (dev k=5 pools, n=40, embedding cache cleared before each call)

| guard() | median | mean | max |
|---|---|---|---|
| without embeddings (`PLANTED_GUARD_EMBED=0`) | 101 ms | 113 ms | 190 ms |
| with embeddings | 1,014 ms | 949 ms | 1,085 ms |

The embedding model takes about 36 s to load once per process (cold start, measured in a fresh process).
The weights (~470 MB) were downloaded once from Hugging Face for tuning. Without them, Guard runs with an
`EMBEDDINGS_UNAVAILABLE` warning. Rules extraction makes no model calls.

### Open issues

1. **Guard does not beat paraphrase (T1) on dev.** T1 campaign pages form about 5 origins out of 5
   (no shared wording, domain family or byline), so at k = 5 the planted answer ties the honest answer
   on origins. G1 and G2 ask for >= 50% relative reduction and >= 10 points below pagevote on T0 **and**
   T1, so they will likely fail on T1. T0 is handled (k50 > 8; 15% flip at k in {3, 5}, all from the
   support regime; see 3). This matches the plan's warning that content similarity alone fails at T1.
   It is a finding to report, not something to tune away on test.
2. **TAU_EMBED = 0.88 is fragile.** It was chosen by 0.6 points (one pool), and only 37% of its
   embedding edges join a true common origin. **Human decision before `prereg-v2`:** keep the rule's pick,
   or switch to 0.92 (13 edges, all joining true common origins). See `docs/guard_thresholds.md`.
3. **The top-answer tie-break by pages reintroduces page counting.** As specified, an origin tie is
   broken by page count, so in the support regime one official origin vs one T0 origin goes to the
   campaign (3 or 5 copies). With GATE_MARGIN = 1 these answers are always CONTESTED and hedged, so they
   are hedged flips, not confident ones. A rank-only tie-break, or abstaining on ties, would remove
   them; this is a design choice for the team before the tag.
4. **Gate cost.** The DATA_VOID gate fires on every honest single-origin pool and every support-regime
   k = 0 pool (one official source). This is by construction (< 2 origins), and the floor only hedges.
   The PREREG G4 cost (over-hedging of *final answers* <= 40%) must be measured on agent runs.
5. **Provenance contributes little on dev.** At TAU_CONTENT = 0.4, content MinHash alone groups T0 copies
   and syndicated wire copies, so `guard_noprov` is close to `guard`. Domain-family edges are 99%
   precise but rarely decisive here. Boilerplate edges remain 78% precise ("Posted in Uncategorised." is
   still generic). Author+date and cited-origin signals never fire on dev, so they are untested on real
   pages.
6. **Untested on test, held-out and Urdu.** No test or held-out page was opened or scored. There are no
   Urdu dev pools, so Urdu clustering (char 5-grams) and Urdu extraction are covered by synthetic tests
   only. T3 (cross-lingual) gets no content edge across languages unless embeddings fire, and those need
   a weak provenance signal.
7. **Contract-test change outside the listed paths.** Wiring `guard` into `apply_defense` broke
   `tests/test_baselines.py::test_guard_not_implemented_yet`. It was replaced by
   `test_guard_branches_return_defense_out`, the minimal edit needed for `pytest -q` to pass.
8. **Extraction** now also requires units for measurement and percentage questions (dev fix; see
   `docs/guard_thresholds.md`). LLM extraction is still not run (prompt hash TODO).

---

## Guard prompt 3 done — FROZEN 6646ef587797e15ea7fdbb841d6ac601f917759bff9dbc34f034026c440b4f99

Written by A; A never opened `data/generator` or `data/heldout`. Dev split only; no model API calls.

- **Team decision (a):** `TAU_EMBED` 0.88 -> **0.92**. On dev, 13 of 13 embedding edges join a true
  common origin, against 37% at 0.88.
- **Team decision (b):** ties in origin count are broken by **best rank, never page count**. A tie always
  emits CONTESTED with a hedge floor of at least "may" (`vote.tally`, `vote.tied`, `core.assemble`; tested).
- **Variant P (paraphrase edges without provenance, TAU_PARA in {0.95, 0.97}): OFF, negative finding.**
  At τ >= 0.95, paraphrase edges cost 0.0 points of false merges for 0.0 points of T1 gain: 256 and 45
  edges, all duplicating content edges. No T1 campaign pair reaches cosine 0.95 (max 0.913). T1 campaign
  and honest pairs have nearly the same cosine (median 0.720 vs 0.735). Details are in
  `docs/guard_thresholds.md`.
- **Final values:** TAU_CONTENT 0.4, TAU_EMBED 0.92, TAU_PARA None, GATE_MARGIN 1, rank tie-break,
  MIN_ORIGINS 2, MinHash 128 perms seed 1. `FROZEN = True`.

| final dev metric (372 pools) | pagevote | guard | guard_noprov |
|---|---|---|---|
| planted-wins k in {3,5}: all / T0 / T1 | 50.0% / 50.0% / 50.0% | 38.1% / 7.5% / 48.3% | 39.4% / 7.5% / 50.0% |
| silent planted-wins (no warning) k in {3,5} | 50.0% | 25.6% | 26.2% |
| clean k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| honest false-merge rate | n/a | 0.1% | 0.0% |
| syndication: 3 wire copies form 1 origin | n/a | 100.0% | 100.0% |
| single-origin k=0 gate rate | 0.0% | 100.0% | 100.0% |

Runtime per query on CPU: median 46 ms without embeddings, 790 ms with embeddings, plus a one-off
~36 s model load.

**Open issues still standing:**
1. Guard does not defend against T1 paraphrase on dev: planted-wins at k in {3, 5} is 48.3% vs 50.0% for
   pagevote, so G1 and G2 are expected to fail on T1. This is reported as a finding.
2. The single-origin and support gate always fires (hedge only). G4's over-hedging of final answers
   must be measured on agent runs.
3. Nothing has been measured on test, held-out or Urdu pages. The LLM extraction prompt hash is TODO.

---

## Offline test evaluation done (2026-11-15)

Run by A. `data/generator/` was not opened. Held-out pages were loaded only through `data.pools.PageBank` /
`MockEngine.from_bank` inside `scripts/eval_guard_test.py`; no held-out page text, title or url was printed or
written, only aggregate metrics (plus aggregate index metadata: which tier/label campaigns each bank has, and the
regimes of the 20 held-out T4 questions). Test split only. Rules extraction, no model API calls.

- **Freeze checks (before and after the run):** `CONFIG_HASH = 6646ef587797e15ea7fdbb841d6ac601f917759bff9dbc34f034026c440b4f99`
  (unchanged); `git diff --stat prereg-v2 -- planted/guard planted/baselines` empty both times.
- **Pools:** held-out 1,278 built (160 T4 pools rejected: the bank has T4 for 20 test questions); main 2,578 built, 0 rejected.
- **Outputs:** `results/guard_offline_heldout.csv`, `results/guard_offline_main.csv`, `results/guard_offline_summary.md`
  (headline tables, decision-level hypothesis table with Holm, extraction check, findings).
- **Decision-level verdicts (held-out):** G2 FAIL (page-vote conjunct passes on T0 only: −55 pts; T1 −7 pts);
  G4 FAIL (single-origin gate hedges 100% of pools; bound 40%); G1 and G3 NOT DECIDABLE OFFLINE (G3's false-merge
  conjunct passes at 1.8%); G6 order holds at decision level, but held-out T4 (20 `known` questions) cannot separate the defenses.
- **Extraction generalisation (rules, not changed):** held-out EN 82.1% of slots, UR 73.8%; main EN 94.9%, UR 82.3%.
- **Deviations:** 4 workers instead of CPU count − 1 (RAM next to concurrent sweeps; the first 7-worker attempt
  failed with OpenBLAS out-of-memory errors). T0 k=5 added as a supplementary decision-level cell, because G1/G2 are
  stated at T0 k=5 but arm G lists no T0 k=5 condition. k50 uses the dev script's linear interpolation, not PREREG §5's logistic fit.
- Embedding vectors cached in `.cache/emb/` (gitignored); `logs/` and `.cache/llm.sqlite` untouched.
