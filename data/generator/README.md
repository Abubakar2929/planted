# data/generator

**Owner:** B — see `PLAN.md` §2.

**Firewall (AGENTS.md §2):** if you work for **C**, do not open, read, grep or summarise `data/generator/` or `data/heldout/`. Breaking this invalidates the paper's results.

Main generator (see `data/README.md` for the outputs and how to use them):

| File | Role |
|---|---|
| `world.py` | the fictional world: syllable names with fixed Urdu spellings, 12 fact types, answers, hedge claims |
| `render.py` | renders Contract-1 pages from a template bank (`data/templates/main_{en,ur}.json`) |
| `generate.py` | CLI: questions + main page bank (`--backend offline|llm`) |
| `llm.py` | seeded, cached LLM rewriting (LiteLLM) with claim-survival checks |
| `embed.py` | similarity for the T4 adaptive attacker (multilingual MiniLM if installed, else char-5-gram TF-IDF) |
| `validate.py` | contract + invariant checks and the similarity report |

The generator never imports anything from `planted/guard/` or `planted/baselines/` (tested in `tests/test_data.py`).
Prompts describe only the threat model ("an operator wants claim X believed"), never a defence.
