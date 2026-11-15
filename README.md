# Planted

Measure and fix poisoned search results in AI search agents: a dose-response benchmark (English + Urdu) and Guard, a drop-in filter that counts independent sources, not pages.

## Quickstart

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then fill in GEMINI_API_KEY and GROQ_API_KEY
python scripts/smoke_keys.py
pytest -q
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then fill in GEMINI_API_KEY and GROQ_API_KEY
python scripts/smoke_keys.py
pytest -q
```

On Windows, clone into a short path (e.g. `C:\src\planted`): torch's nested headers can exceed the
260-character path limit during `pip install` unless Windows long-path support is enabled.

One question through every arm-A dose (18 runs, a few cents; same command on every OS):

```bash
python run.py --arm A --model gflite31 --seed 0 --defense none --mode single --bank data/pages/main --questions data/questions/dev20.jsonl --limit 1
```

Lines are appended to `logs/A-single-gflite31-none-s0.jsonl` (`--overwrite` to start fresh). Every
model call is cached in `.cache/llm.sqlite`, so a rerun is free and logs the same lines. Add
`--dry-run` to see the run count and estimated cost without calling a model.

## Usage

### Use Guard in your agent

```python
from planted.guard import enforce, guard

q = "When was the Yarlodale Basin Water Authority founded?"
results = [  # your retriever's results: url plus title / snippet / content (no other keys needed)
    {"url": "https://northfen-wire.example/1", "title": "Basin authority marks anniversary",
     "snippet": "", "content": "The Yarlodale Basin Water Authority was founded in 1952 to manage the river basin."},
    {"url": "https://valecourier.example/2", "title": "History of the basin authority",
     "snippet": "", "content": "Regional archives show that councillors founded the Yarlodale Basin Water "
                                 "Authority in 1952 after two decades of floods."},
    {"url": "https://quickfacts-blog.example/3", "title": "Basin authority facts",
     "snippet": "", "content": "Some say the Yarlodale Basin Water Authority was founded in 1987."},
]
out = guard(q, results, lang="en")
print(out.system_note)  # Independent-source check: '1952' is supported by 2 pages from 2 independent origin(s); ...
print(out.top_answer, out.origins)  # 1952 {'1952': {'pages': 2, 'origins': 2}, '1987': {'pages': 1, 'origins': 1}}
print(out.warnings, out.hedge_floor)  # ['CONTESTED: the top two answers are within 1 ...'] may
answer = "It was founded in 1952."  # your model's answer, written with out.system_note / out.results in context
print(enforce(answer, out.hedge_floor, "en"))  # This may not be confirmed: It was founded in 1952.
```

`out.results` holds the same results, reordered (Guard reweights and never deletes), each with
`extracted_answer`, `cluster_id`, `guard_score` and a `note`. `out.warnings` carries the data-void /
contested gate (`DATA_VOID: ...`, `CONTESTED: ...`), and `out.hedge_floor` is the minimum hedge the answer
should carry. The hedge reaches the answer only when you call `enforce`. Runs offline: rule-based answer
extraction is the default (`PLANTED_EXTRACT=rules`), and embedding edges use a local
sentence-transformers model when installed (otherwise Guard adds an `EMBEDDINGS_UNAVAILABLE` warning and
skips them). This is a research prototype, not a production filter.

### gpt-researcher in two environment variables

Start the proxy with `planted serve --port 8000`, then in gpt-researcher's environment:

```bash
export RETRIEVER=custom
export RETRIEVER_ENDPOINT="http://127.0.0.1:8000/search?mode=mock_guard&qid=pl-support-009&k=3"
```

```powershell
$env:RETRIEVER = "custom"
$env:RETRIEVER_ENDPOINT = "http://127.0.0.1:8000/search?mode=mock_guard&qid=pl-support-009&k=3"
```

`mode=mock` serves the poisoned mock web without Guard, `mock_guard` the same pages through Guard,
and `passthrough` / `guard` the real web via Tavily or Brave (`TAVILY_API_KEY` / `BRAVE_API_KEY`).
Full steps: [docs/demo_gpt_researcher.md](docs/demo_gpt_researcher.md). Other frameworks (untested
sketches): [LlamaIndex](docs/snippets/llamaindex_postprocessor.py),
[LangChain](docs/snippets/langchain_compressor.py).

### Run the Inspect eval

Register-ready Inspect task: the model is a tool-using search agent (`search`, `open`, `submit`)
over the mock web. Run from the repo root:

```bash
inspect eval planted/inspect_task.py@planted_bench -T k=3 -T split=dev --model google/gemini-3.1-flash-lite --limit 5 --log-dir inspect_logs
```

Options: `-T guard=true`, `-T tier=T0|T1|T3`, `-T label=wire|propaganda|blog`, `-T lang=ur -T split=test`.

## Reproduce every figure

```bash
python -m analysis.analyze logs/ --out results
```

It reads every `logs/*.jsonl` (one Contract-2 line per agent run, written by `run.py`), re-scores
each run with the preregistered rules and writes `results/table1.{md,csv}`, `rates.csv`, `k50.csv`,
`summary.json` and `results/figures/*.png`. Hypotheses without data are reported as "not run".
Raw logs are not committed to git. Recreate them with `run.py` (cached calls replay exactly) or
download the released logs once they are published. The question and page files can be exported
for the Hub with `python scripts/push_hf_dataset.py --repo ORG/NAME` (dry run by default).

## Docs

- [PLAN.md](PLAN.md): team plan, roles, contracts, phases (single source of truth)
- [AGENTS.md](AGENTS.md): rules for coding agents and humans
- [docs/plan-v2.2.md](docs/plan-v2.2.md): long plan with rationale and citations

## Preexisting code

Any code adapted from our earlier project "Refusal Routers" lives in `planted/engine/` and is marked
there as preexisting. Everything else was written for this project.

## Status

- **Guard is implemented, tuned on dev only and frozen** (`CONFIG_HASH` 6646ef58…4f99, preregistered at tag `prereg-v2`).
- **Held-out test pages (decision level, no agent; [results/guard_offline_summary.md](results/guard_offline_summary.md)):** against page voting, planted-answer wins drop from 62.0% to 7.0% on copy-paste (T0) campaigns at k=5, a difference of −55.0 pts (95% CI −65.0 to −45.0; T0 k=5 is a supplementary cell outside the preregistered arm G; at k=8 the difference is −58.0 pts, CI −67.0 to −49.0). On paraphrased (T1) campaigns at k=5 they drop only from 76.0% to 69.0%, −7.0 pts (CI −14.0 to −1.0).
- **The data-void gate hedges every honest single-source answer** (100% of single-origin pools), so G4 failed. We recommend applying the hedge floor (`enforce`) only for high-risk queries.
- **Rule-based answer extraction** is correct on 82% of held-out English page slots and 74% of Urdu ones (100% in-sample on dev).
- **Research prototype.** The LlamaIndex and LangChain snippets are untested. A gpt-researcher integration is provided but has not yet been demonstrated end to end.

## Team roles

| Role | Name | Owns |
|---|---|---|
| A: Harness & Ship | TODO | engine, agent, providers, Inspect task, proxy, CLI, real-web check, CI |
| B: Data & Story | TODO | data, generator, held-out set, intro/related/methods (data), video |
| C: Guard & Evidence | TODO | PREREG, Guard, baselines, analysis, scorecard site, results/discussion |
