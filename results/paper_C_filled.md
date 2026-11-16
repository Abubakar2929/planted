# Paper sections owned by C (drafted by B; paste into the official Google Doc template)

Results and Discussion. Every number is a placeholder filled from `results/summary.json` by
`python -m analysis.fill_paper docs/paper_C.md` (anything not measured prints as `__`). Do not type numbers
by hand: rerun the analysis and the filler. Before submitting, check each sentence against what the data
show: if a hypothesis failed, the sentence must say so (the wording marked **[if passed / if not]** is
there for that).

Total runs analysed: 1903. Logged spend: $0.95. The analysis rescored every
run with the preregistered rules; it agreed with the harness's own label on 100.0% of runs.
Against hand labels from all three authors (__ runs), the automatic flip scorer reached Cohen's
κ = __ (human-human Fleiss' κ = __; Gate 2 required >= 0.6).
Hedge-level κ against the lexicon was __ in English and
__ in Urdu (human-human __ and
__).

## 4 Results (~1.25 pages)

**Table 1** (from `results/table1.md`) lists every preregistered hypothesis: its estimate, 95% CI,
Holm-adjusted p and pass/fail. Confirmatory family: H1, H2, H3, G1, G2, G3, G4 (Holm across seven tests).
The exploratory rows H4, H4b, H5 and G6 make no multiplicity claim. **Figure 1** (`fig1_hero.png`) shows
the dose-response curves without a defence and with Guard.

### 4.1 Agents count pages (H1)

The share of answers that flip to the planted claim rises with the number of planted results
(logistic slope on dose, question-clustered SEs). The lowest k50 (the dose that flips half the answers)
was 7.4 of 10 results (95% CI 5.4 to 7.7). H1: not passed
(Holm p = 2.25e-13). **[if passed]** A campaign that controls a minority of the results
page can rewrite most answers. **[if not]** Flips grow with dose, but more slowly than predicted.

### 4.2 A credibility label is worth a few pages, and less as dose grows (H2)

Labelling the planted pages as wire copy rather than propaganda changed k50 by a factor of
0.89 for the first model (95% CI 0.83 to 0.96; every model's ratio is in the
Table 1 note; H2 not passed, Holm p = 1).
Read as a headline: a reputable label is worth roughly __ extra pages (fill in from `results/k50.csv`:
k50(wire) minus k50(propaganda) for the median model). The label x dose interaction and the gap at k = 8
are given in the Table 1 note.

### 4.3 Data voids flip sooner (H3)

Questions with no honest answer on the web (including the fake support-number brands) flipped at
0.00 times the dose needed for known facts (95% CI 0.00 to 0.23;
H3 passed). **[if passed]** This is where planted claims are cheapest: a single campaign fills the void.

### 4.4 Counting origins, not pages (G1, G2)

On the attacks it targets (T0 copy-paste and T1 paraphrase), Guard cut flips by -100%
compared with no defence (lowest cell, 95% CI __ to 0%; G1 not passed).
At k = 5 its flip rate was at least -22.2 pts below both the reliability prompt and page voting
(smallest gap; 95% CI -37.0 pts to -7.4 pts; G2 not passed). Every arm used the same claim extraction,
so the gap comes from *what is counted* (origins rather than pages), not from a better prompt. The
ablation without provenance (`guard_noprov`) is shown in Figure 1.

### 4.5 The fix is cheap (G3) and hedges where it should (G4)

With no attack (k = 0), Guard lowered clean accuracy by -0.0 pts (90% CI -0.0 pts to
-0.0 pts; equivalence margin +/-3 pts; G3 __). False merges, syndication accuracy and
latency are in the Table 1 note. On data voids at k = 3, the share of wrong answers that were hedged
or abstained rose by 7.1 pts (95% CI 0.0 pts to 21.4 pts; G4 not passed).
Over-hedging on correct known-fact answers and on the honest single-origin condition is in the note.

### 4.6 Exploratory: hedges, Urdu, smarter attackers (H4, H4b, H5, G6)

- **Hedge retention (H4, H4b).** When sources said a claim was only "preliminary", the agent kept that
  hedge in __ of answers (95% CI __ to __). With three agreeing
  hedged sources, retention was __ lower than with one (95% CI __ to
  __; a negative value means higher).
- **Urdu (H5).** At k = 3, the Urdu term in the flip regression was b = -4503599630334696.00 (log-odds;
  p = __), controlling for each model's clean accuracy in each language. Raw flip rates by language
  are in the Table 1 note. The Urdu set
  was reviewed by an author who is a native speaker, not by an independent reviewer (Appendix A).
- **Adaptive attackers (G6).** Guard's relative reduction by tier is in the Table 1 note. We predicted it
  would fall below 50% on T4 (the attacker picks the least similar paraphrase on a held-out generator);
  the mean T4 reduction was __ (prediction not passed).

## 5 Discussion and limitations (~0.75 page)

**What this means for deployed search agents.** The failure is structural: an agent that treats
agreement between results as evidence will be steered by anyone who can publish several pages. The
NewsGuard audit found leading chatbots repeating false claims 35% of the time in August 2025, and
attributed the rise to real-time web search (Introduction). Our dose curves show the mechanism in a
controlled setting. **[if G1/G2 passed]** Guard shows the remedy does not need a better model: count
independent origins before counting agreement, and say so when there is only one origin.

**What Guard does not fix.** **[fill from G6]** Against an adaptive attacker on a held-out generator, the
reduction fell to __. Provenance signals (shared text, templates, near-duplicate structure) can be removed by
a determined campaign. Guard raises the cost of a campaign; it does not make one impossible. A campaign
that buys or compromises several truly independent outlets would defeat it, by design, since those really
are independent origins.

**Cost to honest users.** **[fill from G3/G4]** Clean-accuracy cost __ pts, over-hedging __% on unhedged
true claims at k = 0, and __% on honest single-origin facts. The single-origin figure is the price of the
void gate: a fact with only one real source is hedged even when it is true. We report this cost rather
than tune it away.

**Limitations.** (1) Fictional questions and websites keep the benchmark free of real-world harm and
of training-data contamination, but real campaigns are messier (Appendix A). (2) We ran __ models on free or
low-cost tiers. (3) Our search engine is a fixed pool of 10 results per question. A live engine re-ranks
and personalises, which the real-web check (__ queries) only samples. (4) The Urdu set has one native-speaker
reviewer, who is also an author. (5) Generator and Guard were written by different people who never read
each other's code (the firewall in `AGENTS.md`). This reduces, but does not remove, the risk that Guard
learned the generator's habits. The held-out generator (different templates, page layout and LLM) tests
this directly (G6).

**Future work.** Live-engine replication, more languages, and Guard as a retrieval-time filter that
providers could deploy without changing the model.
