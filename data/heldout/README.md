# data/heldout

**Owner:** B — see `PLAN.md` §2.

**Firewall (AGENTS.md §2):** if you work for **C**, do not open, read, grep or summarise `data/generator/` or `data/heldout/`. Breaking this invalidates the paper's results. (C *uses* `data/heldout/pages/` only through `data/pools.py`, at test time, never for tuning.)

Held-out test generator for the Guard sweep (PLAN.md firewall rule (c)):

- `templates_{en,ur}.json`: a **new template bank**, written separately from `data/templates/`, from the threat model only.
- `generate_heldout.py`: its own renderer with a **different page architecture** (forum threads, press releases, FAQ pages, listicles, news briefs), different chrome, outlet naming, domain patterns and T0 domain-family scheme; LLM tiers use a **different model family** (GPT-OSS-120B on Groq) from the main bank (Gemini).
- `pages/`: the output (test split only: 100 EN questions, the Urdu 60, T4 for 20 questions).

```bash
python -m data.heldout.generate_heldout --seed 0                  # offline (committed)
python -m data.heldout.generate_heldout --seed 0 --backend llm    # needs GROQ_API_KEY
python -m data.generator.validate --bank data/heldout/pages
```

Audit trail: `git log -- data/heldout data/generator` must show only `[B]` commits.
