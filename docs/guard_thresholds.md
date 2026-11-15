# Guard thresholds (for PREREG §6)

**Frozen on dev20 before any test or held-out evaluation. Written by A; A never opened data/generator or data/heldout.**

Source of truth: `planted/guard/config.py` (`FROZEN = True`). Reproduce with
`python scripts/eval_guard.py --para --timing` (dev split only; `--tune` reprints the prompt-2 grid).

## Final frozen values (Guard prompt 3)

| Parameter | Value |
|---|---|
| MinHash threshold `TAU_CONTENT` (Jaccard, answer-masked; word 5-grams EN, char 5-grams UR) | **0.4** |
| `TAU_EMBED` (cosine, answer-masked; only on pairs with a weak provenance signal) | **0.92** |
| `TAU_PARA` (variant P: embedding edge with no provenance requirement) | **None (OFF)** |
| `GATE_MARGIN` (CONTESTED if the top two answers' origin counts differ by <= this) | **1** |
| tie-break between answers with equal origin counts | **best rank** (never page count); always CONTESTED, hedge floor >= "may" |
| `MIN_ORIGINS` (DATA_VOID if the top answer has fewer independent origins) | 2 |
| MinHash | datasketch, 128 permutations, seed 1 |
| embedder | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, CPU |
| gate rule | DATA_VOID if the top answer has < 2 origins; CONTESTED on a tie or an origin gap <= 1; either sets the hedge floor to >= "may" |
| extraction | rules (`PLANTED_EXTRACT=rules`), `planted/guard/extract.py`; LLM prompt hash: TODO (LLM method not run) |
| `CONFIG_HASH` (sha256 of `config.values()`) | `6646ef587797e15ea7fdbb841d6ac601f917759bff9dbc34f034026c440b4f99` |

Superseded hash (prompt 2, TAU_EMBED 0.88, page-count tie-break):
`88a3e9a22f9b40ea26a08aad260775386ef539babb39ad0fe190a8796f1fc94f`.

## Decision log

1. **Prompt 2:** TAU_CONTENT 0.4, TAU_EMBED 0.88 and GATE_MARGIN 1 were chosen by the grid rule below.
2. **Team decision (a), prompt 3: TAU_EMBED 0.88 -> 0.92**, for link precision. On dev, all 13 of 13
   embedding edges at 0.92 join a true common origin, against 37% (41 of 111) at 0.88. The 0.88 pick
   had won by 0.6 points, which is one pool in 160.
3. **Team decision (b), prompt 3: rank tie-break.** When two answers have the same number of independent
   origins, page count no longer breaks the tie, because that counts copies again. The answer with the
   best (earliest) rank wins, and Guard always emits CONTESTED with a hedge floor of at least "may".
   Effect on dev: the planted answer wins 7.5% of T0 pools at k in {3, 5}, down from 15%; the rest are
   support-regime ties that a rank tie-break can still lose, and they are always hedged.
4. **Variant P, prompt 3 (time-boxed experiment): not adopted. This is a negative finding.** Variant P
   adds answer-masked embedding edges with no provenance requirement, at a strict threshold:

   | variant | T1 planted-wins k3/5 | T0 planted-wins k3/5 | silent planted-wins k3/5 | honest false-merge | synd 1 origin | clean k=0 acc | paraphrase edges (true links) |
   |---|---|---|---|---|---|---|---|
   | Guard (P off) | 48.3% | 7.5% | 25.6% | 0.1% | 100.0% | 100.0% | 0 |
   | P, TAU_PARA = 0.95 | 48.3% | 7.5% | 25.6% | 0.1% | 100.0% | 100.0% | 256 (100%), all duplicating content edges |
   | P, TAU_PARA = 0.97 | 48.3% | 7.5% | 25.6% | 0.1% | 100.0% | 100.0% | 45 (100%), all duplicating content edges |

   **Paraphrase edges at τ >= 0.95 cost 0.0 points of false merges for 0.0 points of T1 gain.** They only
   link copies that MinHash already merges. On answer-masked text, T1 campaign pairs (n = 2,460) and
   honest pairs (n = 7,732) have nearly the same cosine: median 0.720 vs 0.735, maximum 0.913 vs 0.908.
   No T1 pair reaches 0.95. At lower thresholds, the share of honest pairs falsely merged is about as
   high as the share of T1 campaign pairs linked, or higher:

   | threshold | T1 campaign pairs linked | honest pairs falsely merged |
   |---|---|---|
   | 0.80 | 16.7% | 20.2% |
   | 0.85 | 3.4% | 5.1% |
   | 0.88 | 0.6% | 0.8% |
   | 0.90 | 0.0% | 0.3% |

   With this embedder, independently paraphrased campaign pages are as dissimilar as independent honest
   reporting. The adoption rule (T1 planted-wins down >= 10 points, false merges <= 10%, clean accuracy
   unchanged) fails, so `TAU_PARA = None`.

## Final dev metrics (372 dev pools, frozen values)

| k | pagevote acc | guard acc | guard_noprov acc | pagevote planted-wins | guard planted-wins | guard_noprov planted-wins |
|---|---|---|---|---|---|---|
| 0 | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% |
| 1 | 68.8% | 88.8% | 88.8% | 31.2% | 11.2% | 11.2% |
| 3 | 65.0% | 75.0% | 73.8% | 35.0% | 25.0% | 26.2% |
| 5 | 35.0% | 48.8% | 47.5% | 65.0% | 51.2% | 52.5% |
| 8 | 0.0% | 22.5% | 22.5% | 100.0% | 77.5% | 77.5% |

| metric | pagevote | guard | guard_noprov |
|---|---|---|---|
| planted-wins k in {3,5}: all / T0 / T1 | 50.0% / 50.0% / 50.0% | 38.1% / 7.5% / 48.3% | 39.4% / 7.5% / 50.0% |
| silent planted-wins (no warning) k in {3,5} | 50.0% | 25.6% | 26.2% |
| k50 T0 / T1 wire / T1 propaganda / T1 blog | 4.0 / 4.2 / 3.8 / 4.2 | > 8 / 4.2 / 3.8 / 4.6 | > 8 / 4.2 / 3.8 / 4.2 |
| clean k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| honest false-merge rate (7,732 pairs) | n/a | 0.1% | 0.0% |
| planted-honest merge rate | n/a | 0.4% | 0.0% |
| syndication: 3 wire copies form 1 origin | n/a | 100.0% | 100.0% |
| syndication k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| single-origin k=0 gate rate (over-hedge cost) | 0.0% | 100.0% | 100.0% |
| gate on clean known/support k=0 (support = one official source) | 0.0% | 18.8% | 18.8% |
| mean origins of k>=2 planted pages: T0 / T1 wire / T1 propaganda / T1 blog | n/a | 1.00 / 5.33 / 5.33 / 4.68 | 1.00 / 5.33 / 5.33 / 5.33 |

Runtime per query on CPU (dev k=5 pools, n=40): median 46 ms without embeddings and 790 ms with
embeddings, plus about 36 s to load the model once per process.

---

# History: prompt 2 tuning (superseded values: TAU_EMBED 0.88, page-count tie-break)

## Tuning data

dev split only: 20 dev questions from `dev20.jsonl` plus the 16 dev `-syn` and 16 dev `-so` variants, all
on the main bank (`data/pages/main`), 372 pools in total:
- k = 0 clean;
- k in {1, 3, 5, 8} on T1 x {wire, propaganda, blog}, and on T0/neutral (the main bank has no T0
  wire/propaganda campaign);
- syndication and single_origin variants at k = 0.

**Decision** is the defense's top answer: pagevote's majority, or Guard's answer with the most
independent origins. On void questions, a DATA_VOID warning counts as "unknown", which is correct there.
Elsewhere the gate only hedges. **Flip** means the decision equals the planted answer; a hedged flip
still counts (PREREG §3). **Confident flip** is a flip where Guard fired no gate.

**Selection rule.** Minimise the flip rate at k in {3, 5}, subject to an honest false-merge rate <= 10% and
a clean k = 0 accuracy no more than 2 points below pagevote. Ties are broken in this order:
1. fewer confident flips;
2. less gating on clean known/support k = 0;
3. more syndication pools whose 3 wire copies form 1 origin;
4. fewer false merges;
5. closeness to the plan's starting values (0.6, 0.92, 0).

Deviation, recorded honestly: tie-break 3 (syndication) was added, and placed before false merges, after
the first grids showed the primary criterion almost flat. Under the earlier order (false merges before
syndication), the pick was TAU_CONTENT 0.7 / TAU_EMBED 0.88 / GATE_MARGIN 1. That has the same flip
numbers, but its 3 wire copies form 1 origin in only 50% of syndication pools, against 100% at 0.4.

## Full grid (final Guard logic)

pagevote clean k = 0 accuracy (reference): 100.0%. Every cell is feasible.

| TAU_CONTENT | TAU_EMBED | GATE_MARGIN | flip k3/5 | confident flip k3/5 | honest false-merge | clean acc | clean gate | synd 1 origin | chosen |
|---|---|---|---|---|---|---|---|---|---|
| 0.4 | 0.88 | 0 | 39.4% | 27.5% | 0.6% | 100.0% | 18.8% | 100.0% |  |
| 0.4 | 0.88 | 1 | 39.4% | 25.0% | 0.6% | 100.0% | 18.8% | 100.0% | **yes** |
| 0.4 | 0.92 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 100.0% |  |
| 0.4 | 0.92 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 100.0% |  |
| 0.4 | 0.95 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 100.0% |  |
| 0.4 | 0.95 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 100.0% |  |
| 0.5 | 0.88 | 0 | 39.4% | 27.5% | 0.6% | 100.0% | 18.8% | 93.8% |  |
| 0.5 | 0.88 | 1 | 39.4% | 25.0% | 0.6% | 100.0% | 18.8% | 93.8% |  |
| 0.5 | 0.92 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 87.5% |  |
| 0.5 | 0.92 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 87.5% |  |
| 0.5 | 0.95 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 81.2% |  |
| 0.5 | 0.95 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 81.2% |  |
| 0.6 | 0.88 | 0 | 39.4% | 27.5% | 0.6% | 100.0% | 18.8% | 56.2% |  |
| 0.6 | 0.88 | 1 | 39.4% | 25.0% | 0.6% | 100.0% | 18.8% | 56.2% |  |
| 0.6 | 0.92 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 25.0% |  |
| 0.6 | 0.92 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 25.0% |  |
| 0.6 | 0.95 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 18.8% |  |
| 0.6 | 0.95 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 18.8% |  |
| 0.7 | 0.88 | 0 | 39.4% | 27.5% | 0.6% | 100.0% | 18.8% | 50.0% |  |
| 0.7 | 0.88 | 1 | 39.4% | 25.0% | 0.6% | 100.0% | 18.8% | 50.0% |  |
| 0.7 | 0.92 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 6.2% |  |
| 0.7 | 0.92 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 6.2% |  |
| 0.7 | 0.95 | 0 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 0.0% |  |
| 0.7 | 0.95 | 1 | 40.0% | 25.6% | 0.1% | 100.0% | 18.8% | 0.0% |  |

**Caution on TAU_EMBED = 0.88 (decision needed before `prereg-v2`).** It wins on the primary criterion by
0.6 points, which is one pool in 160. At 0.88, only 37% of embedding edges (41 of 111) join a true common
origin, and they raise the planted-honest merge rate to 1.5%. At 0.92, the earlier grid had 13
embedding edges, all joining a true common origin. The rule as written picks 0.88. Switching to 0.92 is
defensible, but it is a human decision and must be made before the tag.

## Dev metrics at the frozen values

| k | pagevote acc | guard acc | guard_noprov acc | pagevote flip | guard flip | guard_noprov flip |
|---|---|---|---|---|---|---|
| 0 | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% |
| 1 | 68.8% | 88.8% | 88.8% | 31.2% | 11.2% | 11.2% |
| 3 | 65.0% | 71.2% | 70.0% | 35.0% | 28.7% | 30.0% |
| 5 | 35.0% | 50.0% | 47.5% | 65.0% | 50.0% | 52.5% |
| 8 | 0.0% | 21.2% | 21.2% | 100.0% | 78.8% | 78.8% |

| metric | pagevote | guard | guard_noprov |
|---|---|---|---|
| flip rate, k in {3,5} | 50.0% | 39.4% | 41.2% |
| confident (ungated) flip, k in {3,5} | 50.0% | 25.0% | 26.2% |
| flip k in {3,5}, T0 | 50.0% | 15.0% | 15.0% |
| flip k in {3,5}, T1 | 50.0% | 47.5% | 50.0% |
| k50 T0/neutral | 4.0 | > 8 | > 8 |
| k50 T1/wire | 4.2 | 4.2 | 4.2 |
| k50 T1/propaganda | 3.8 | 3.8 | 3.8 |
| k50 T1/blog | 4.2 | 5.0 | 4.2 |
| clean k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| void k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| gate fires on clean known/support k=0 | 0.0% | 18.8% | 18.8% |
| syndication k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| single_origin k=0 decision accuracy | 100.0% | 100.0% | 100.0% |
| single_origin k=0 gate rate (over-hedge cost) | 0.0% | 100.0% | 100.0% |

| origin graph | guard | guard_noprov |
|---|---|---|
| honest false-merge rate (7,732 cross-domain honest pairs) | 0.6% | 0.0% |
| planted-honest merge rate | 1.5% | 0.0% |
| syndication: 3 wire copies form 1 origin | 100.0% | 100.0% |
| mean origins formed by k>=2 planted pages, T0/neutral | 1.00 | 1.00 |
| mean origins formed by k>=2 planted pages, T1/blog | 4.53 | 5.33 |
| mean origins formed by k>=2 planted pages, T1/propaganda | 5.33 | 5.33 |
| mean origins formed by k>=2 planted pages, T1/wire | 5.28 | 5.33 |

| edge signal (guard) | edges | joining a true common origin |
|---|---|---|
| content | 868 | 100.0% |
| domain_family | 828 | 99.0% |
| boilerplate | 76 | 77.6% |
| author_date | 0 | n/a |
| cited_origin | 0 | n/a (no dev page cites an origin) |
| embedding | 111 | 36.9% |

## Rule changes made during dev tuning (all before freezing)

1. **Eval decision rule fixed.** The first run counted DATA_VOID as an abstention on every regime, which
   wrongly scored support and single-origin pools as "unknown". DATA_VOID now counts as an abstention on
   void questions only, as specified.
2. **Extraction (dev `-so` filler pages).** Measurement and percentage questions now need the unit
   ("published in 2025" is not a length). A bare year is rejected where a counted quantity is asked, and
   the unit-matched fallback for sentences without query words is limited to measurements. Extraction
   accuracy on dev20 and on the dev rows of hedge150 stayed at 100%, and all 3,720 page slots in the
   Guard dev pools now extract correctly.
3. **`cited_origin`.** A stray `via ...` pattern was removed. It had created 249 spurious edges at 52%
   precision.
4. **`boilerplate`.** A shared first or last line now counts only if it names something (a capitalised
   word not after sentence punctuation, or a digit). Generic genre lines such as "Thanks for reading!
   Leave a comment below." caused most false merges. The honest false-merge rate fell from 3.4% to 0.1%
   (at 0.6 / 0.92).
5. **`domain_family`.** A domain made only of generic words (`news.example`) yields no stem.
