# Planted

Measure and fix poisoned search results in AI search agents: a dose-response benchmark (English + Urdu) and Guard, a drop-in filter that counts independent sources, not pages.

## Quickstart

```bash
python -m venv .venv
# activate: source .venv/bin/activate  (Windows: .venv\Scripts\activate)
pip install -e ".[dev]"
cp .env.example .env        # then fill in your keys
python scripts/smoke_keys.py
pytest -q
```

## Docs

- [PLAN.md](PLAN.md): team plan, roles, contracts, phases (single source of truth)
- [AGENTS.md](AGENTS.md): rules for coding agents and humans
- [docs/plan-v2.2.md](docs/plan-v2.2.md): long plan with rationale and citations

## Preexisting code

Code adapted from our earlier project "Refusal Routers" will live in `planted/engine/` and is marked there as preexisting.

## Team roles

| Role | Name | Owns |
|---|---|---|
| A: Harness & Ship | TODO | engine, agent, providers, Inspect task, proxy, CLI, real-web check, CI |
| B: Data & Story | TODO | data, generator, held-out set, intro/related/methods (data), video |
| C: Guard & Evidence | TODO | PREREG, Guard, baselines, analysis, scorecard site, results/discussion |
