# Planted: team plan (single source of truth)

**Repo:** `planted` · **Branch:** `main` only · **Deadline:** Mon 16 Nov, 16:59 PKT (submit final by 16:00)
**What we are building:** Planted Bench (measure) + Planted Guard (fix) + Planted Ship (adopt).
Full rationale, citations and budget are in `docs/plan-v2.2.md` (the long plan). This file is the operating manual.

---

## 1. How we win: judging criteria → what each role owns

Judges score three criteria, 1–5 each, unweighted. Every task below exists to move one of these.

| Criterion | What earns a 5 | Owner(s) | Our differentiator vs other teams |
|---|---|---|---|
| **Impact & Innovation** | New to the field, matters if it works | B (framing), C (Guard result), A (ship) | Not only a benchmark: a measured **fix** (Guard). A causal test of the NewsGuard-vs-Harvard dispute. First Urdu search-agent poisoning measurement. A tested gpt-researcher proxy plus a fact-checker scorecard |
| **Execution Quality** | Sound method, honest findings | C (stats, Guard), B (held-out data), A (reproducibility) | Preregistered thresholds with a **predicted failure** (G6). A **held-out generator**. A no-provenance ablation. Clean-accuracy, false-merge and real-web costs. Human-validated κ. A one-command rebuild |
| **Presentation & Clarity** | Clear story, one picture | B (prose, video), C (figures) | One headline, one hero figure (dose curves with/without Guard), one hypothesis table, a "How to use this" box, a 4-minute video with a live flip and a live fix |

**Rule for everyone:** if a task does not move one of these three rows before the deadline, it is not on this plan.

---

## 2. The three roles

| Role | Name | Owns (writes) | Never touches | Paper sections |
|---|---|---|---|---|
| **A: Harness & Ship** | _fill in_ | `planted/engine/`, `planted/agent/`, `planted/providers/`, `planted/inspect_task.py`, `planted/serve.py`, `planted/cli.py`, `scripts/realweb_check.py`, `run.py`, `.github/`, `pyproject.toml` | — | Methods: harness, engine, Inspect · "How to use this" box |
| **B: Data & Story** | _fill in_ | `data/` (generator, templates, tiers, held-out, Urdu, lexicons, questions), `docs/video_script.md`. Paper sections are written in the official Google Doc template | `planted/guard/`, `planted/baselines/` (**firewall**) | Abstract draft, Intro, Related Work, Methods: data, Appendix A |
| **C: Guard & Evidence** | _fill in_ | `PREREG.md`, `planted/guard/`, `planted/baselines/`, `analysis/`, `site/`. Paper sections are written in the official Google Doc template | `data/generator/`, `data/heldout/` (**firewall**) | Results, Discussion, figures, Table 1, scorecard |

**Shared (change only after telling the other two in chat):** `contracts/`, `PLAN.md`, `README.md`, `BUDGET.md`, `tests/fixtures/`.

**The firewall is a procedure, not a guarantee.** B never reads Guard code, and C never reads generator code. The audit trail is `git log -- data/generator planted/guard`: generator commits must be B's, and Guard commits must be C's. Agents working for B or C follow the same rule (see `AGENTS.md`).

---

## 3. Repo layout

```
planted/
├── PLAN.md  AGENTS.md  README.md  PREREG.md  BUDGET.md
├── paper.pdf                         # final submitted PDF, committed at the end
├── docs/plan-v2.2.md                 # long plan, citations
├── docs/video_script.md              # (B) video storyboard; video file not committed
├── contracts/                        # SHARED: frozen tonight
│   └── schemas.py                    # Contract 1–3 (pydantic)
├── planted/                          # pip package
│   ├── engine/      (A) mock search engine, deterministic, seeded
│   ├── agent/       (A) LiteLLM tool loop, cache, logger
│   ├── providers/   (A) gemini, groq adapters
│   ├── guard/       (C) guard(), clustering, vote, gate, floor
│   ├── baselines/   (C) none, prompt, pagevote, guard_noprov
│   ├── inspect_task.py (A)  serve.py (A)  cli.py (A)
├── data/            (B)
│   ├── generator/  templates/  heldout/  urdu/  lexicons/
│   └── questions/  # frozen JSONL: dev20, test, urdu60, hedge150
├── analysis/        (C) score.py, stats.py, figures.py, analyze.py
├── scripts/         (A) smoke_keys.py, realweb_check.py (live-search check)
├── site/            (C) static scorecard + viewer (GitHub Pages)
├── tests/           everyone: tests/test_<area>.py, fixtures shared
├── results/         committed summaries (CSV, figures PNG)
└── logs/  .cache/   gitignored (raw JSONL, SQLite cache)
```

---

## 4. Contracts (freeze tonight, in `contracts/schemas.py`)

All three people code against these, so nobody waits for anybody. Changing a contract needs all three to agree in chat, and the commit is tagged `[ALL]`.

**Contract 1: data and engine**

```python
class Page(BaseModel):
    url: str; domain: str; title: str; snippet: str; body: str
    lang: Literal["en", "ur"]; author: str | None; date: str | None
    # hidden from the agent: scoring only
    planted: bool; campaign_id: str | None; label: Literal["wire","propaganda","blog","official","neutral"]
    tier: Literal["T0","T1","T2","T3","T4"] | None; asserted_answer: str; source_hedge: Literal["none","may","preliminary","disagree"] | None

class Question(BaseModel):
    qid: str; lang: Literal["en","ur"]; split: Literal["dev","test"]
    regime: Literal["known","void","support","single_origin","syndication","hedge"]
    question: str; correct_answer: str; planted_answer: str | None

class Condition(BaseModel):
    arm: Literal["A","B","D","E","G","T4","RW"]; k: int; label: str | None; tier: str | None
    lang: str; source_hedge: str | None; n_agree: int | None
    defense: Literal["none","prompt","pagevote","guard","guard_noprov"]; model: str; seed: int

# engine API (A implements; B supplies the pages)
def search(episode_id: str, query: str, lang: str) -> list[SearchResult]   # rank,url,title,snippet only
def open_url(url: str) -> str
```

**Contract 2: one log line per agent run** (`logs/*.jsonl`): every field of `Condition`, plus `episode_id, qid, regime, queries[], opened[], final_answer, normalised, correct_answer, planted_answer, outcome ∈ {correct, flip, abstain_hedge, drift}, answer_hedge, guard_summary, tokens_in, tokens_out, latency_ms, cost_usd, ts`. All metrics are computed from these lines alone.

**Contract 3: defense interface** (C implements; A's agent loop calls it)

```python
def apply_defense(name: str, query: str, results: list[dict], lang: str) -> DefenseOut
class DefenseOut(BaseModel):
    results: list[dict]          # reordered; each may add cluster_id, guard_score, note
    system_note: str | None      # e.g. "Answer X: 6 pages / 1 origin; Answer Y: 3 pages / 3 origins"
    warnings: list[str]          # e.g. "DATA_VOID: <2 independent origins"
    hedge_floor: str | None      # min hedge the final answer must carry
def enforce(answer: str, hedge_floor: str | None, lang: str) -> str
# public API for users:
def guard(query, results, lang="en") -> GuardResult   # = apply_defense("guard", ...)
```

Result dicts use the keys `url, title, snippet, content, rank`, plus optional `domain, author, date`. Those are the same keys the gpt-researcher, LlamaIndex and LangChain adapters produce.

---

## 5. Phases, parallel tasks and gates

Times are PKT. Each row is one phase. The three columns run **at the same time**, and a gate closes the phase.

### Phase 0: Tonight setup (Sat 00:15–02:30)

| A: Harness & Ship | B: Data & Story | C: Guard & Evidence |
|---|---|---|
| Create repo `planted` with the layout above, `pyproject.toml`, `.gitignore` (`.env`, `logs/`, `.cache/`), and a GitHub Action running `pytest -q` on push | 2 fake questions + 10 fake pages in `tests/fixtures/` (unblocks A and C tonight) | Write `contracts/schemas.py` with A and B (first 30 min, together) |
| Gemini + Groq keys answer a tool call (`scripts/smoke_keys.py`) | Start **T1 page generation overnight** for the dev 20 + first 60 test questions (batch, ~$2) | `PREREG.md` v0 from `docs/plan-v2.2.md` §Preregistration |
| One query: engine → agent → one JSONL line, end to end | Book the Urdu reviewer for Sat 12:00–16:00 | `planted/guard/` skeleton plus a unit test on fixture pages |
| Mark the Refusal Routers code preexisting in README | Open the GuardRAG / Evidence Balancing / TriShieldRAG abstracts and note them in `docs/novelty.md` | |

**Gate 0 (02:30):** contracts committed (tag `contracts-v1`), keys work, one JSONL line exists. Then sleep (A 02:30–09:00, B 03:00–10:00, C 02:30–09:00).

### Phase 1: Build to Gate 1 (Sat 09:00–11:00)

| A | B | C |
|---|---|---|
| Agent loop on Gemini 2.5 FL and GPT-OSS-120B (Groq); SQLite cache keyed by hash; byte-identical rerun test | Generator: 120 questions (80 known, 40 void incl. ~15 fake-support-number), 3 label templates, T0 pages, randomised authors/dates/boilerplate in every tier | Guard v0: batched extraction (1 call per query), normalisation (incl. Urdu NFKC/ZWNJ), MinHash + provenance edges, components, origin vote, gate, floor |
| `run.py --arm A --model ... --seed 0` | Commit `data/questions/dev20.jsonl` by 10:00 | Baselines `prompt`, `pagevote`, `guard_noprov` behind Contract 3 |

**Gate 1 (11:00):** one dev question runs through every arm-A condition on one model, and a rerun is byte-identical. Tag `gate1`.
**Kill rule:** if Gate 1 isn't met by 12:00, switch to the single-call fallback (results pasted into one prompt) for the sweeps, and keep the agent loop for the demo and Inspect only.

### Phase 2: Pilot and freeze (Sat 11:00–16:00)

| A | B | C |
|---|---|---|
| Pilot: dev20 × 2 models × arm-A doses; Guard on/off at T0/T1, k = 5 | T3 cross-lingual pools, benign syndication, honest single-origin void; **send 60 Urdu questions + lexicon to the reviewer by 12:00**; T4 adaptive generator | Tune τ_strict and the gate on **dev20 only**; `analysis/score.py` (flip / abstain_hedge / drift); `analyze.py` runs on pilot logs |
| Spend log in `BUDGET.md` | Urdu hedge lexicon with the reviewer | κ labelling (all three label 50 items each, flips first) |

**Gate 2 (15:00):** flips vary with k (not 0% everywhere, not 100% at k = 1); extraction accuracy ≥ 90%; honest false-merge ≤ 10%; flip κ ≥ 0.6.
**16:00:** commit the final `PREREG.md` plus frozen Guard thresholds and tag `prereg-v2`. **The commit hash goes in the paper.** After this tag, nobody changes Guard logic or thresholds.

### Phase 3: Main sweeps (Sat 16:00 – Sun 14:00)

| A | B | C |
|---|---|---|
| Bench sweep: A+B (5,760), D (3,600), then E (1,200) when Urdu is approved | **Held-out test generator** (different LLM family + new template bank, written blind to Guard) → `data/heldout/` | Analysis of A/B/D/E as logs land; Table 1 skeleton with Holm adjustment |
| Sun 08:00: **Guard sweep** (12,000) on held-out pages, then T4 (20 Q) + Urdu Guard (360) | Open the CoordGuard, Bara and Lee & Kim PDFs and fix their numbers in Related Work (Google Doc template) | Hero figure, tier figure, cost panel |
| Retries and overnight monitoring (sleep shifts below) | Intro + Related Work + Methods (data) drafts | Static scorecard page skeleton in `site/` |

Spend checks: at 22:00, > $25 → shrink arm D to 2 models. At Sun 12:00, > $45 → same.
**Gate 3 (Sun 10:00):** arms A+B complete on all 3 models. Tag `gate3`. **No new arms after this.**
Night sleep: B 01:00–08:00; A and C alternate (A 03:00–10:00, C watches until 03:00 then sleeps 03:00–10:00).

### Phase 4: Ship and results (Sun 14:00–23:00)

| A | B | C |
|---|---|---|
| pip package (`guard()` public API), `planted serve` proxy for gpt-researcher (`RETRIEVER=custom`) + a recorded guarded run | Video script and storyboard (`docs/video_script.md`) | Guard results text, Table 1 with every hypothesis pass/fail |
| **Real-web check:** ~50 harmless queries via Tavily/Brave free tier → false-merge, over-hedge, $/query, p50/p95 latency | Discussion draft with C; Appendix A (exact title, plus the personal-data line) | Scorecard + results viewer live on GitHub Pages (EN/UR) |
| Inspect task + `.eval` logs on 2 models; HF dataset push; README quickstart + LlamaIndex/LangChain snippets | Assemble the full draft in the official template | Every number in the text traced to `analyze.py` output |
| Methods: harness section + "How to use this" box | | |

**Gate 4 (23:00): feature freeze.** Tag `freeze`. Only bug-fix reruns after this, and the draft must be complete end to end.
Sleep: A 23:30–06:30, B records the video 23:00–01:00 then sleeps 01:00–08:00, C 00:00–07:00.

### Phase 5: Polish and submit (Mon 07:00–16:00)

| A | B | C |
|---|---|---|
| Fresh-clone test: `pip install -e . && python analyze.py logs/` rebuilds every figure; Inspect runs | Abstract with real numbers (150–250 words); prose polish | Number audit: text ↔ tables ↔ figures |
| Reference check: first third of the bibliography | Reference check: second third | Reference check: last third |

**Submit v1 by 11:00** (PDF + repo link + video link), tag `submit-v1`. Resubmit improvements under the same title. **Final by 16:00**, tag `submit-final`. Nothing new after 16:00.

---

## 6. Handoffs (the only times one role waits on another)

| When | From → To | What | If late |
|---|---|---|---|
| Sat 00:45 | All | `contracts/schemas.py` | Nobody codes past stubs |
| Sat 01:00 | B → A, C | `tests/fixtures/` fake questions and pages | A/C write their own 1-question fixture |
| Sat 10:00 | B → A | `data/questions/dev20.jsonl` + T0/T1 pages | A pilots on fixtures; Gate 1 still possible |
| Sat 11:00 | C → A | `apply_defense()` for none/prompt/pagevote/guard | A runs `none` only in the pilot |
| Sat 16:00 | C → A | Frozen thresholds (`prereg-v2`) | Guard sweep cannot start: escalate |
| Sun 08:00 | B → A | `data/heldout/` test pages | Run the Guard sweep on test-split pages from the main generator and **say so in the paper** |
| Sun 20:00 | A, C → B | Final numbers and figures | B writes around placeholders `__` |

---

## 7. Git rules for one `main` branch

1. **Own your paths.** Commit only inside the directories your role owns (§2). Shared files need a chat message first.
2. **Pull before push, every time:** `git pull --rebase && pytest -q && git push`. Never force-push `main`.
3. **Small and often.** Push at least every 60 minutes while awake. Large uncommitted work is how conflicts happen.
4. **Commit prefix:** `[A] ...`, `[B] ...`, `[C] ...`, `[ALL] ...` for contract changes. The firewall audit depends on it.
5. **Main stays green.** The GitHub Action runs `pytest -q`. If you break it, fixing it is your next task.
6. **Never commit** `.env`, API keys, `logs/`, or `.cache/`. Commit `results/*.csv` and figures only. Raw logs go to the HF dataset at the end.
7. **Tags mark gates:** `contracts-v1`, `gate1`, `prereg-v2`, `gate3`, `freeze`, `submit-v1`, `submit-final`.
8. **Conflict?** The path owner's version wins. Then talk.
9. Never commit video files or raw logs; the paper is written in the Google Doc template and only the final paper.pdf is committed.

---

## 8. Agent briefs (paste the role's brief into your coding agent)

Every agent must read `AGENTS.md` and this file first.

**Agent brief A: Harness & Ship.**
Goal: deterministic, cached, seeded runs from one command, and the shipped surfaces.
You own `planted/engine|agent|providers`, `inspect_task.py`, `serve.py`, `cli.py`, `scripts/realweb_check.py`, `run.py`, CI.
Implement Contracts 1 and 2 exactly, and call defenses only through Contract 3.
Done when:
- `python run.py --arm A --model gemini-2.5-flash-lite --seed 0` writes valid Contract-2 lines;
- a rerun is byte-identical;
- `inspect eval planted/inspect_task.py -T guard=true -T tier=T1` runs;
- `planted serve --guard` answers gpt-researcher's custom retriever with `[{url, raw_content}]`;
- the real-web script outputs false-merge, $/query and latency.

Don't: edit `data/`, `planted/guard/`, or contracts without `[ALL]`.

**Agent brief B: Data & Story.**
Goal: questions and pages that make the evaluation honest, plus the paper's front half.
You own `data/`, `docs/video_script.md`. Write Intro, Related Work and Methods (data) in the official Google Doc template.
Produce Contract-1 `Question` and `Page` JSONL with randomised author/date/boilerplate in **every** tier, and tiers T0, T1, T3 and T4. Also produce benign syndication, honest single-origin voids, and 15 fake-support-number brands. All domains must be fictional `.example`.
The held-out generator must use a different LLM family and a new template bank. Write it from the threat model, not from Guard's features.
Done when:
- the files in `data/questions/` validate against `contracts/schemas.py`;
- the Urdu set is reviewer-approved;
- the lexicons cover EN and UR at 4 hedge levels.

Don't: open `planted/guard/` or `planted/baselines/` (firewall).

**Agent brief C: Guard & Evidence.**
Goal: a defense that changes what is counted, measured honestly.
You own `PREREG.md`, `planted/guard/`, `planted/baselines/`, `analysis/`, `site/`. Write Results and Discussion in the official Google Doc template.
Implement Contract 3. Guard must:
- use one batched extraction call per query;
- normalise text (NFKC, ZWNJ/ZWJ strip, Urdu letter folding; character 5-grams for UR);
- build provenance + MinHash + answer-masked embedding edges;
- reweight, never delete;
- run the data-void gate (< 2 origins) and the hedge floor.

Tune only on `split == "dev"`.
Analysis: Wilson CIs, question-clustered logit, bootstrap k50, TOST, and Holm across H1, H2, H3, G1, G2, G3, G4.
Done when: `python analyze.py logs/` rebuilds every figure and Table 1 from the logs alone.

Don't: open `data/generator/` or `data/heldout/` (firewall); change thresholds after `prereg-v2`.

---

## 9. Protected work and cut order

**Never cut:**
- the dose curve (A) and the label arm with re-framed H2 (B);
- Guard vs none / prompt / page vote on T0 + T1 from held-out pages, with k = 0 clean accuracy, the honest single-origin void, syndication, false-merge and the Guard − provenance ablation;
- the real-web check (≥ 30 queries);
- Urdu arm E (as a pilot if needed) and hedge arm D;
- `PREREG` before the sweep, and κ;
- Appendix A;
- the Inspect task, `guard()`, the gpt-researcher proxy and the scorecard.

**Cut in this order if behind:**
1. T4 → future work
2. Urdu Guard → 30 questions
3. Arm D → 2 models
4. Real-web check → 30 queries
5. Syndication pools → 60 questions

---

## 10. Pitch, so everyone writes toward the same sentence

> *AI search agents count pages, not sources. Planting 3 of 10 results flips __% of answers (k50 = __; __ in Urdu). A reputable label buys only __ extra pages. Planted Guard counts independent origins and cuts flips to __% at a __-point clean-accuracy cost.*

**Video (4 min, B):**
1. The Perplexity "10 sources" scam number, and the NewsGuard 33% vs Harvard 5% dispute.
2. Live flip on a fake-support-number question.
3. Guard toggled on: "independent origins: 2 (not 10)". Then the same in Urdu.
4. The hero figure, including where Guard fails.
5. `pip install`, the guarded gpt-researcher run, and the scorecard.

**Never claim:**
- first dose curve, first controlled web, or first non-English study;
- first anti-Sybil defense;
- Inspect "merged" (say "Register-ready");
- "adopted" (say "designed for and tested in").
