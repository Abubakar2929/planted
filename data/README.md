# data

**Owner:** B (see `PLAN.md` §2). **Firewall:** C never opens `data/generator/` or `data/heldout/` (AGENTS.md §2).
C may read the *outputs* listed below (`questions/`, `pages/`, `heldout/pages/`, `lexicons/`, `pools.py`).

Everything is fictional: invented entities, people and outlets, all domains `*.example`, every phone
number inside the `+1-555-0100..0199` range reserved for fiction. No real outlet, person, brand or
government body is named or imitated; `python -m data.generator.validate` enforces this with a blocklist.

## Files

| Path | What | Count |
|---|---|---|
| `questions/dev20.jsonl` | dev questions (Guard is tuned on these only) | 20 (13 known, 4 void, 3 support) |
| `questions/test.jsonl` | test questions | 100 (67 known, 21 void, 12 support) |
| `questions/single_origin.jsonl` | honest single-origin variant of every known/support fact (`qid` + `-so`) | 95 |
| `questions/syndication.jsonl` | benign-syndication variant (`qid` + `-syn`) | 95 |
| `questions/urdu60.jsonl` | Urdu versions of 60 test questions (`qid` + `-ur`) | 60 (40 known, 12 void, 8 support) |
| `questions/hedge150.jsonl` | true findings for the hedge arm (regime `hedge`) | 150 (20 dev, 130 test) |
| `pages/main/` | main page bank: `pages.jsonl` (Contract-1 `Page`), `index.jsonl`, `manifest.json` | 15,392 pages |
| `heldout/pages/` | held-out page bank for the Guard sweep, test split only | 7,071 pages |
| `lexicons/hedge_{en,ur}.json` | 4-level hedge lexicons + qualifiers; helper `lexicons/lexicon.py` | |
| `urdu/` | reviewer packet and review status for the Urdu set | |
| `pools.py` | `build_pool(bank, question, condition)` -> the 10 results for one episode | |

`index.jsonl` has one line per page: `qid, url, role, tier, label, slot, lang, hedge`. Roles: `honest`,
`official` (support brands), `filler` (pages about the entity that never state the fact), `syndicated`
(one wire story on 3 domains), `planted`, `hedge`. Pages carry Contract 1's hidden scoring fields
(`planted`, `campaign_id`, `label`, `tier`, `asserted_answer`, `source_hedge`); the engine must strip them.

## Regimes

- **known**: a well-covered fact: 10 independent honest pages (mixed outlet labels).
- **void** (data void): no page states the fact; `correct_answer = "unknown"`. Only planted pages answer.
- **support** (fake-support-number brands, 15): the brand's official site states the real number; nothing else does.
- **single_origin**: a known/support fact with exactly one true source (the honest single-origin void, G4's cost).
- **syndication**: 3 identical wire copies of the truth (one origin) + up to 3 independent honest pages.
- **hedge**: a finding stated by 1 or 3 independent pages at a given source-hedge level.

## Pool composition (`data/pools.py`, used by A's engine)

`k` planted pages always come from **one** campaign: `condition.tier` x `condition.label` (label defaults
to `neutral`). The rest of the 10 results:

| regime | other results |
|---|---|
| known | (10-k) honest |
| void | (10-k) fillers |
| support / single_origin | the one true source + (9-k) fillers |
| syndication | 3 syndicated + up to 3 honest + fillers; planted pages replace fillers first, then honest |
| hedge | `n_agree` pages at `source_hedge` + fillers |

Every pool has 10 different domains. Order is a deterministic shuffle keyed by
`(seed, qid, k, tier, label, ...)`; the engine may re-rank. Planted pages available per campaign: 8, so `k <= 8`.

```python
from data.pools import PageBank, build_pool, load_questions
bank = PageBank.load("data/pages/main")                  # Guard sweep: PageBank.load("data/heldout/pages")
q = load_questions("data/questions/test.jsonl")[0]
pages = build_pool(bank, q, condition)                   # condition: contracts.schemas.Condition
```

## Attacker tiers (planted campaigns)

Every page in every tier has a randomised outlet (name and domain drawn as a matched pair), author,
date, boilerplate, genre, length and sentence order. A campaign shares only the claim, plus in T0 a
copied article and a domain-family stem.

| Tier | Main bank | Held-out bank |
|---|---|---|
| T0 copy-paste | one article copied verbatim to 8 sites of one domain family (`stem-news`, `stemdaily`, ...); site chrome differs | same idea, different family scheme (`stem-headlines`, `stem247`, ...) and layouts |
| T1 paraphrase | 8 independent rewrites per label (`wire`, `propaganda`, `blog`, `neutral`; Urdu: `wire`, `propaganda`, `neutral`) | 8 independent rewrites, label `neutral` |
| T3 cross-lingual | one campaign alternating EN and UR pages (UR questions: UR and EN) | same |
| T4 adaptive | per slot, 6 candidates; keep the one least similar to the campaign so far, after a claim-survival check | 20 test questions |

Measured similarity (word-5-gram Jaccard, `python -m data.generator.validate`):

| pair type | main mean | main share >= 0.6 | held-out mean | held-out share >= 0.6 |
|---|---|---|---|---|
| two independent honest pages | 0.028 | 0% | 0.030 | 0% |
| two T0 pages (copy-paste) | 0.609 | 54.5% | 0.790 | 100% |
| two syndicated copies | 0.539 | 5% | 0.728 | 99.2% |
| two T1 pages (paraphrase) | 0.028 | 0% | 0.029 | 0% |
| two T4 pages (adaptive) | 0.018 | 0% | 0.017 | 0% |

So copying is lexically visible, paraphrase is as dissimilar as independent honest reporting, and the
adaptive tier is slightly further apart again, which is the escalation the preregistration (G6) needs.

## Regenerate

```bash
python -m data.generator.generate --seed 0                  # main bank + all question files (offline, ~15 s)
python -m data.heldout.generate_heldout --seed 0            # held-out bank (offline, ~2 s)
python -m data.generator.validate                           # main bank: contracts + invariants + similarity
python -m data.generator.validate --bank data/heldout/pages
python -m data.urdu.make_review_packet                      # reviewer CSVs
```

The committed banks were built with the **offline** backend and the `char5-tfidf` T4 embedder (see each
`manifest.json`). Generation is deterministic: the same seed reproduces every file byte for byte
(`tests/test_data.py::test_regeneration_is_byte_identical`; set `PLANTED_EMBEDDER=tfidf` if
sentence-transformers is installed, so T4 uses the recorded embedder).

### LLM backend (paraphrase tiers written by a model)

```bash
# .env (git-ignored): GEMINI_API_KEY=... (main) and GROQ_API_KEY=... (held-out)
python -m data.generator.generate --seed 0 --backend llm --llm-tiers T1 --llm-langs en ur        # Gemini 3.1 Flash-Lite
python -m data.heldout.generate_heldout --seed 0 --backend llm --llm-tiers T1 --llm-langs en --max-calls 960   # GPT-OSS-120B (Groq)
```

With `--backend llm`, the page text of the chosen tiers is written by the model (temperature 0.9, a random
persona per page, seeded) and wrapped in the same randomised outlet chrome as offline pages. **T1 bodies
are label-agnostic**: the prompt and seed do not depend on the label, so one body serves the wire,
propaganda, blog and neutral variants of a slot, and labels differ only in source branding (the label
effect is isolated from content). Every rewrite must pass the same checks as the validator
(`data/generator/checks.py`): planted answer present, true answer absent, no hedge marker, no real outlet
or brand, phone numbers only in the fiction range. T4 candidates also pass an LLM yes/no check. Failures
retry with a new seed, then fall back to the template page. Each page's origin is recorded in
`index.jsonl` (`gen: llm | template`) and summarised in the manifest (`written_by`, `llm_rejections`).

Calls are cached by `sha256(model, seed, messages)` (A's `planted/agent/cache.py` once implemented, else
`.cache/data_llm_cache.sqlite`), so a rerun costs nothing and an interrupted run resumes where it stopped.
Free tiers: calls are throttled (Groq 9 s apart, Gemini 4.5 s; override `PLANTED_LLM_MIN_INTERVAL`),
rate limits are waited out, and when a daily quota is reached the run stops calling the model and writes
the remaining pages from templates; rerunning the next day upgrades them from the cache plus new calls.
Measured on 2026-11-14: Groq's free tier allows 1,000 requests/day and 8,000 tokens/min.

**Models.** `gemini-2.5-flash-lite` (the plan's main model) returns *404: no longer available to new
users* for new API keys, so the main generator uses `gemini-3.1-flash-lite` (on the plan's roster).
`gemini-3.5-flash-lite` works only without a temperature parameter. T0 stays templated in both backends
(copy-paste is not an LLM attack). The held-out bank uses a different model family (GPT-OSS) from the main
bank (Gemini). Spend goes in `BUDGET.md` ($0 on free tiers; estimated list-price cost is also logged).

**Status:** see each bank's `manifest.json` (`backend`, `llm_scope`, `written_by`) for which pages are
LLM-written. T3 and T4 stay template-generated (free-tier quotas cannot cover them in the sprint).
As of 2026-11-14 (both runs stopped at the daily quota; rerunning resumes from the cache):
main bank (Gemini) T1: 1,148 / 3,840 EN and 303 / 1,440 UR pages LLM-written; held-out bank (GPT-OSS) T1:
410 / 800 EN. The rest are template pages, marked `gen: template`, so results can be split by writer.

## Hedge lexicons

`lexicons/hedge_en.json` and `hedge_ur.json` define 4 levels (`none < may < preliminary < disagree`),
markers for each level, an abstention list, and the templated qualifier used by Guard's hedge floor.
`lexicons/lexicon.py` gives `detect_hedge(text, lang)`, `qualify(answer, level, lang)`, `is_abstention`,
and `normalise` (NFKC, ZWNJ/ZWJ removed, Urdu letter folding, diacritics stripped). Every hedge template
in both banks is detected at its own level, and no unhedged page in either bank contains a marker (both
are validator checks). English "May" (the month) is masked before matching.

## Urdu

60 Urdu questions plus Urdu pages for every role, written directly in Urdu (names come from syllables that
each carry a fixed Urdu spelling, not machine transliteration). **Reviewer status: pending.**
`urdu/review_questions.csv` and `urdu/review_lexicon.csv` are the reviewer packet;
`python -m data.urdu.make_review_packet --apply "<reviewer name>"` records the verdicts in
`urdu/review_status.json`. Until that file says `"approved": true`, the paper must describe the Urdu set
as checked by the authors only.
