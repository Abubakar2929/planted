# Hand-off A → B: test runs, Guard offline results, deviations

Prepared by A, 2026-11-15. No new analysis here. Counts come from the log files; Guard numbers are copied
from `results/guard_offline_summary.md`.

## What ran

Free-tier test sweeps (`python run.py --grid free`, TEST split only, prompt style `neutral`, seed 0), all on
2026-11-15, 16:40–18:13 UTC (21:40–23:13 PKT). Models: **gflite31** (Gemini 3.1 Flash-Lite, team Gemini
free keys) and **gptoss** (GPT-OSS-120B, team Groq free keys). In total **1,903 test runs** against ~23,100 in
the full plan. The reason is the free-tier quotas: Gemini allows 500 requests/day per key, and Groq allows
200k tokens/day per key. The full design needs paid tiers (`docs/progress_A.md` §A5, §A10).

| part | arm | model | valid / planned | error lines in `logs/errors.jsonl` (type only) | outcomes: flip / correct / abstain_hedge / drift |
|---|---|---|---|---|---|
| P1 AB | A | gflite31 | **960 / 960** | none | 286 / 245 / 416 / 13 |
| P2 G | G | gflite31 | **787 / 800** | 64 × AuthenticationError (13 episodes never logged) | 125 / 395 / 242 / 25 |
| P3 REP | A + G | gptoss | **67 / 180** (8 questions) | 4 × RateLimitError (all later logged); the rest stopped cleanly on quota | 15 / 52 / 0 / 0 |
| P4 UR | E | gflite31 | **89 / 180** | 91 × AuthenticationError (91 episodes never logged) | 27 / 30 / 32 / 0 |
| P5 D, P6 G2 | D, G | — | **not run** (cut: free-tier quota) | — | — |

All lines validate against Contract 2. There are 0 invalid lines and 0 duplicate episode ids.

**P1 by k** (n = 60 at k = 0, otherwise 180), flip / correct / abstain_hedge / drift: k0 0/47/0/13 · k1 40/110/30/0 ·
k2 43/48/89/0 · k3 42/25/113/0 · k5 51/8/121/0 · k8 110/7/63/0.

**P2 by defense × condition** (flip / correct / abstain_hedge / drift, n in brackets):

| defense | clean k0 | T0 k3 | T1 k3 | T1 k5 | single_origin k0 |
|---|---|---|---|---|---|
| none | 0/32/0/8 (40) | 8/12/19/0 (39) | 9/1/30/0 (40) | 13/0/26/0 (39) | 0/40/0/0 (40) |
| prompt | 0/32/0/7 (39) | 8/19/13/0 (40) | 8/3/27/0 (38) | 11/0/29/0 (40) | 0/39/0/0 (39) |
| pagevote | 0/32/0/8 (40) | 7/24/7/1 (39) | 9/7/23/1 (40) | 15/0/24/0 (39) | 0/40/0/0 (40) |
| guard | 0/32/7/0 (39) | 7/27/6/0 (40) | 11/20/7/0 (38) | 19/0/21/0 (40) | 0/35/3/0 (38) |

**P3** (gptoss): arm A has 39 runs (none at k0, and T1 k3 and k8 × wire / propaganda); arm G has 28 runs ({none, guard} × {T0, T1} k3).
The flips are A T1 k8 (7/7 propaganda, 7/8 wire) and G none T1 k3 (1/7). Every other run was `correct`.

**P4 (Urdu pilot) is not balanced.** n per lang × k: EN k0 13, k3 21, k8 22; UR k0 10, k3 14, k8 9 (18 UR
and 25 EN questions). There are matched EN/UR pairs for only 8 / 11 / 9 questions at k = 0 / 3 / 8.
Outcomes (f/c/a/d): EN k0 0/13/0/0 · k3 6/1/14/0 · k8 15/0/7/0; UR k0 0/10/0/0 · k3 0/6/8/0 · k8 6/0/3/0.

## Where the data is

- `logs/test_free_P1.jsonl` … `P4.jsonl`: test runs. They are gitignored, so **A will send `logs_test.zip`**
  (these four files only: no errors log, no keys, no cache).
- `results/guard_offline_heldout.csv`, `results/guard_offline_main.csv` and `results/guard_offline_summary.md` (in git).
- `logs/pilot_A*.jsonl` is the **dev** pilot (dev20), **NOT test**. `analysis/analyze.py` drops it by split.
- κ pack: `dist/kappa_pack.zip`. **κ sample drawn from the dev pilot log as preregistered** (`logs/pilot_A.jsonl`,
  PREREG §3). It holds 50 English flip items, identical sheets for A, B and C, and a README. There is no hedge
  sheet, because the pilot has no arm-D runs. To build the key for `kappa score`, re-run
  `python -m analysis.kappa sample <dir holding only pilot_A.jsonl> --out <dir>` (seed 0, deterministic).

## Headline numbers already available (decision level, held-out bank, copied from the summary)

Guard is not compared with "no defence" here: page vote stands in as a proxy. These numbers are not agent flip rates.

- Planted-wins, pagevote vs guard (95% CI): T0 k5† 62.0% [53.0, 71.0] vs **7.0% [3.0, 12.0]**, −55.0 pts
  [−65.0, −45.0]. T0 k8 75.0% vs 17.0%, −58.0 [−67.0, −49.0]. T1 k5 76.0% [67.0, 84.0] vs **69.0% [60.0, 78.0]**,
  −7.0 [−14.0, −1.0]. T1 k8 100.0% vs 97.0%, −3.0 [−7.0, +0.0]. Guard counts a T1 campaign as 5.38 [5.32, 5.42]
  origins (T0: 1.00).
- Costs: clean k0 decision accuracy 97.0% [93.0, 100.0] (unchanged vs pagevote). Honest false-merge
  1.8% [1.4, 2.3]. The single-origin k0 gate fires in 100.0% of pools.
- Verdicts: **G2 FAIL** (T0-only pass; T1 −7 pts; p 0.0165, Holm 0.0165). **G4 FAIL** (single-origin
  over-hedging 100% > 40%, by construction). **G1, G3 NOT DECIDABLE OFFLINE** (G3 false-merge conjunct PASS,
  p 0.0005, Holm 0.0010). **G6** order holds (exploratory), and the T4 < 50% prediction is met. Both outcomes are as
  PREREG predicted for T1.

## Deviations (all of them; for the paper's deviations section)

1. **Roster and sizes.** Free-tier keys only (gflite31, gptoss). About 1,900 of ~23,100 planned runs were made. P3 (gpt-oss
   replication) is partial at 67/180, P4 (Urdu pilot) is partial at 89/180, and P5 (arm D) and P6 (T3/T0 k8/T1 k8) were not run.
   As a result, H4/H4b (arm D) have no data, and only gflite31 covers arm G.
2. **Question selection.** Questions were drawn by a regime-stratified seed-0 shuffle (largest-remainder quotas;
   60 = 40 known / 13 void / 7 support; nested 20 ⊂ 40 ⊂ 60; Urdu 30 = 20/6/4), instead of all 100 test questions.
3. **P2 single_origin substitutions (8).** Void questions have no `-so` variant: pl-void-003→pl-known-028-so,
   pl-void-004→pl-known-034-so, pl-void-006→pl-known-069-so, pl-void-010→pl-support-004-so,
   pl-void-018→pl-known-076-so, pl-void-021→pl-support-008-so, pl-void-022→pl-known-014-so,
   pl-void-023→pl-known-060-so.
4. **P2: 13 runs failed after retries** and are reported as missing. They are excluded from denominators (PREREG §7).
   The logged error type is `AuthenticationError` (P4's 91 missing runs show the same type).
5. **Episode-id suffix `-neutral`.** This is cosmetic: `single_call.DEFAULT_STYLE` is `hedge_ok`, so non-default styles get a suffix.
   Every test run used the preregistered neutral prompt.
6. **P2 restart.** After an out-of-memory crash, P2 was resumed with 2 workers. It resumed from the log and lost no data
   (0 duplicate ids, 0 invalid lines).
7. **Offline Guard eval.** It used 4 workers instead of CPU−1 = 7 (RAM; this does not affect any number). A supplementary
   T0 k=5 cell was added (a PREREG gap: G1/G2 are stated at T0 k=5, but arm G lists no T0 k=5). k50 uses linear
   interpolation, not PREREG §5's logistic fit.
8. **Firewall.** One automated `ls` showed held-out file NAMES (not contents) in A's session. Nothing was opened.
9. **Extraction generalisation.** The rules extractor scored 100% on dev and 82.1% on held-out EN slots, 73.8% on held-out UR and 94.9% on main EN.
10. **Held-out T4** exists for only 20 questions, all in the known regime (160 T4 pools rejected). It cannot separate the defenses.
11. **Packaging.** `data/` was added to the `pyproject` packaging (commit 061a822). No data changed.

## Commands for B

```bash
mkdir handoff && unzip logs_test.zip -d handoff     # -> handoff/logs/test_free_P1..P4.jsonl
python -m analysis.analyze handoff/logs --out results
#   -> results/table1.md, table1.csv, rates.csv, k50.csv, summary.json, results/figures/*.png
python -m analysis.fill_paper docs/paper_C.md --results results --out results/paper_C_filled.md
#   (same for docs/paper_B.md); missing fields print as __ and are listed
```

Point `analyze` at a folder that holds only the test logs, because it reads every `*.jsonl` under the folder.
