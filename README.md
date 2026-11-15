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
from planted import guard

results = [{"url": "https://a.example/1", "title": "...", "snippet": "...", "content": "..."},
           {"url": "https://b.example/2", "title": "...", "snippet": "...", "content": "..."}]
out = guard("When was the Yarlodale Basin Water Authority founded?", results, lang="en")
print(out.system_note, out.warnings)  # evidence summary: answers by independent origin
```

`out.results` holds the same results, reordered (Guard reweights and never deletes), each with
`cluster_id` and `guard_score`; `out.hedge_floor` is the minimum hedge the answer should carry.
This is a research prototype, not a production filter.

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

Research prototype.

- Bench harness (mock engine, cached single-call runner, sweep grids), the `planted serve` proxy,
  the CLI and the Inspect task are implemented and unit-tested.
- Guard: to be tested on the Planted mock web and through gpt-researcher. At the time of writing,
  `planted.guard` is a stub that raises `NotImplementedError` (`planted serve`'s `/health` reports
  `guard_available`), so the Guard example above does not run yet.
- LlamaIndex and LangChain snippets are untested interface sketches.
- No results are claimed here; see the paper and `results/` once the sweeps are run.

## Team roles

| Role | Name | Owns |
|---|---|---|
| A: Harness & Ship | TODO | engine, agent, providers, Inspect task, proxy, CLI, real-web check, CI |
| B: Data & Story | TODO | data, generator, held-out set, intro/related/methods (data), video |
| C: Guard & Evidence | TODO | PREREG, Guard, baselines, analysis, scorecard site, results/discussion |
