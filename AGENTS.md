# Rules for coding agents working in this repo

Read `PLAN.md` first, then the agent brief for your role in `PLAN.md` §8. These rules apply to every agent and every human. (Claude Code users can copy this file to `CLAUDE.md`.)

1. **Know your role.** Your human will tell you whether you work for A (Harness & Ship), B (Data & Story) or C (Guard & Evidence). Write only inside that role's paths, listed in `PLAN.md` §2.
2. **Firewall.**
   - If you work for **B**, do not open, read, grep or summarise `planted/guard/` or `planted/baselines/`.
   - If you work for **C**, do not open, read, grep or summarise `data/generator/` or `data/heldout/`.

   This is part of the paper's methods, so breaking it invalidates our results.
3. **Contracts are frozen.** Code against `contracts/schemas.py`, and do not edit it. If a contract seems wrong, stop and tell your human.
4. **One branch.** Work on `main`. Before every push, run `git pull --rebase && pytest -q`, and push only if the tests pass. Never force-push. Prefix commit messages with `[A]`, `[B]` or `[C]`.
5. **Determinism.** Every model call goes through the cache in `planted/agent/` with an explicit seed. Do not add unseeded randomness. Data generators take `--seed`.
6. **No secrets, no raw logs in git.** Keys live in `.env` (gitignored). Never commit `logs/` or `.cache/`.
7. **Fictional only.** All domains are `*.example`. Never generate pages that impersonate a real outlet, person, brand or government body. Fake-support-number questions use invented brands only.
8. **No tuning on test data.** Thresholds and prompts are tuned only on `split == "dev"`. After the `prereg-v2` tag, do not change Guard logic, thresholds or the PREREG file.
9. **Honest outputs.** Never invent numbers, citations or results. If something wasn't run, write `__` or `TODO`, not an estimate.
10. **Small steps.** Make one task at a time and add a test for it. Each commit should leave the repo runnable.
11. **Cost awareness.** Before any sweep, print the planned run count and estimated cost, and log actual spend to `BUDGET.md`.
