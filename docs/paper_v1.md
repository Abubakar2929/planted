# Planted: AI Search Agents Count Pages, and Counting Origins Only Partly Fixes It

*Preregistered at git tag `prereg-v2` (commit `80f81562a583a82239dc2a8106fff20f216b07a5`). Every number in
Results comes from `python -m analysis.analyze` on the test logs (`results/table1.md`, `results/summary.json`)
or from the frozen offline Guard evaluation (`results/guard_offline_summary.md`).*

## Abstract

When several search results repeat a claim, AI search agents tend to believe it, even when every page
comes from one campaign. We measure this causally and test a fix. **Planted Bench** is a fully fictional
mock web in English and Urdu. We vary how many of ten results carry a planted claim (the dose), how those
pages are labelled, and whether honest coverage exists at all. With Gemini 3.1 Flash-Lite answering from
ten results, planting 3 of 10 pages cut correct answers on well-covered facts from 100% to 12%: the agent
mostly hedged or reported both answers rather than adopting the lie (1% flips; 51% at 8 planted pages).
Where no honest page existed (data voids), a single planted page flipped every answer (39 of 39), the one
confirmatory hypothesis that passed with the data we could collect. A "wire service" label made planted
pages more persuasive than a "propaganda" label, not less (70% vs 35% flips at 8 planted pages). **Planted Guard** groups results into
independent origins from provenance and content, and counts origins instead of pages. In a frozen
decision-level test on held-out pages, it cut planted wins on copy-paste campaigns from 62% to 7% at no
clean-accuracy cost, but barely moved independently paraphrased campaigns (76% to 69%), as we
preregistered. With the agent in the loop, Guard turned hedges into correct answers (T0, 3 planted
pages: 68% correct vs 31% undefended), but did not reduce flips. Free-tier limits allowed 1,903 of about
23,100 planned runs, so most Guard hypotheses fail or remain incomplete. We report all of them.

## 1 Introduction

In December 2025, an AI answer engine told users that a scam phone number was an airline's official
support line, citing ten sources that were one seeded campaign. Two audits of live AI tools disagree on
why such failures happen. NewsGuard found the ten leading AI tools repeating false claims 35% of the time
in August 2025, up from 18% a year earlier, while their non-response rate fell from 31% to 0%, and tied the
shift to real-time web search (NewsGuard, 4 September 2025). A Harvard Kennedy School study found that only
5% of chatbot responses supported Kremlin disinformation and blamed *data voids*, topics with little
reliable coverage (Alyukov et al.). The two explanations call for different fixes, and neither audit can
separate them, because both observe the web as it is.

We separate them causally. In a controlled mock web we vary, independently, the **dose** (how many of the
ten results carry a planted claim), the **label** (wire service, propaganda network, anonymous blog) and
the **regime** (well-covered fact, data void, fake support number), in English and in Urdu. Everything is
invented, so no model can know the answers in advance and no real person, outlet or brand is involved.

Measuring the failure is not enough. Prior work shows that repetition can beat credibility (Schuster et
al.) and that coordinated poison defeats consistency defences (Li, Guo and Xu). We ask whether an agent
can be made to count *sources* instead of pages without deleting suspected clusters. **Planted Guard**
estimates independent origins from provenance and content, votes by origin, gates confident answers when
fewer than two origins agree, and enforces a hedge floor.

**Contributions.** (1) A dose-response benchmark for search-agent poisoning with labels, data voids and
Urdu, and a fitted k50 (the dose that flips half the answers). (2) A causal test of the data-void
explanation: voids flip at the first planted page. (3) An origin-counting defence evaluated at the
decision level and with an agent, with its costs, and with a preregistered failure on paraphrased
campaigns that the data confirm. (4) Open artefacts: a one-function `guard()`, a gpt-researcher proxy, a
Register-ready Inspect task, the generator and both page banks, and a bilingual scorecard.

## 2 Related Work

**Repetition, credibility and search agents.** Schuster, Gautam and Markert show, across 373 fictional
entities and 13 models, that models rank government above newspapers above social media, but that
repeating a low-credibility source reverses this ordering. HAE-GEO builds a 72k-page poisoned web,
documents a "corroboration trap", and finds that defensive prompting increases verification but rarely
recovers the right answer. Zhang, Triedman and Shmatikov find a short user-generated URL cited in 38-51% of
deep-research reports. We add a fine-grained dose with k50, credibility labels, data voids and Urdu, and
test a defence that is not a prompt.

**Coordinated poisoning and independence.** CoordGuard shows that coordinated poison forms a dense
embedding component that consistency defences miss: RobustRAG and ReliabilityRAG reach an
exposure-conditional attack success rate of 0.512 against 0.576 undefended, and always filtering
suspected clusters lowers it to 0.167 at a 13.6-point clean-accuracy cost (Li, Guo and Xu). GuardRAG prunes
near-duplicate clusters in static RAG (Jiao et al.). Bara formalises why more reports need not mean more
evidence: a report-space deduplication mechanism tracks representation similarity far more than true
evidential ancestry. Lee and Kim show that lexical deduplication catches near-identical sybils but not
polymorphic ones, and that abstention and drift carry 47-66% of output mass; we adopt their
flip / abstain-or-hedge / drift split. Guard differs in setting (web-search agents rather than static RAG),
in signal (provenance edges as a proxy for ancestry, alongside content) and in action (reweight and gate
rather than delete). Our results reproduce Bara's and Lee and Kim's warning: paraphrased campaigns look
like independent reporting.

**Other defences and certainty.** RobustRAG's certificate assumes poisoned passages are a minority (Xiang
et al.); Evidence Balancing rebalances retrieved documents by stance, not by source (Yang et al.);
single-source rewriting distorts certainty (Belem et al.); CLEAR measures knowledge-conflict persuasion in
ten languages, not including Urdu.

## 3 Planted Bench

**World and questions.** All entities, people, outlets and domains are invented; domains use the reserved
`.example` suffix and phone numbers the fiction range +1-555-0100..0199. Names are built from syllables
with fixed Urdu spellings, giving consistent English and Urdu forms. There are 120 facts: 80 *known* facts
(eight types, each covered by ten independent honest pages), 25 *data voids* (no page states the answer;
the correct behaviour is to abstain) and 15 *fake-support-number* brands (only the brand's official site
states the real number). 20 facts form the dev split; Guard was tuned on these only. Known and support
facts also have an *honest single-origin* variant (exactly one true source) and a *benign syndication*
variant (one wire story on three domains).

**Pages and attacker tiers.** Every page has a randomised outlet, author, date, boilerplate, genre, length
and sentence order. **T0** copies one article to eight sites of one domain family. **T1** writes eight
independent paraphrases under three labels; in the main bank 1,148 of 3,840 English T1 pages were written
by Gemini 3.1 Flash-Lite (the rest by templates, marked per page). **T3** mixes English and Urdu pages in
one campaign; **T4** keeps, for each page, the candidate least similar to the campaign so far. Two T0
pages share word 5-grams with mean Jaccard 0.61; two T1 pages share 0.03, the same as two independent
honest pages. Guard's test pages come from a **held-out generator** written blind to Guard (new template
bank, page architecture and outlet scheme; LLM-written T1 by GPT-OSS-120B). The data author never read
Guard's code and the Guard author never read the generator; this firewall is a procedure we followed,
auditable in the commit history.

**Agent and runs.** A single-call agent searches once (query = question), receives the ten results (after
the defence, if any), and answers with one prompt, preregistered after a dev pilot: *"Answer the question
in one short line based on the search results."* (temperature 0, seed 0). Models: Gemini 3.1 Flash-Lite
(`gflite31`) and GPT-OSS-120B (`gptoss`) on free tiers. Arm A crosses k in {0, 1, 2, 3, 5, 8} with three
labels on 60 test questions (40 known, 13 void, 7 support); arm G compares no defence, a reliability
prompt, page vote and Guard on held-out pages for 40 test questions; arm E is an English/Urdu pilot.

**Scoring.** A run is a *flip* if the answer states the planted answer (also when hedged; such runs are
reported as hedged flips), *correct* if it states only the correct answer (never for voids),
*abstain/hedge* if it abstains, hedges or states both answers, and *drift* otherwise. The scorer is
deterministic (`analysis/score.py`). Statistics: Wilson intervals, logistic regression with
question-clustered SEs, k50 from a logistic fit with a question bootstrap (2,000 resamples), TOST for
equivalence, Holm correction over seven confirmatory hypotheses.

## 4 Planted Guard

Guard takes the ten results and builds an origin graph. Two pages are linked when they share a
provenance signal (registrable domain or domain family, a named boilerplate line, a cited origin,
identical author and time) or when their answer-masked text is near-identical (MinHash Jaccard >= 0.4 on
word 5-grams, character 5-grams for Urdu); an answer-masked embedding edge (cosine >= 0.92) is added only
on pairs that already carry a weak provenance signal. Connected components are origins. Each candidate
answer is supported by its number of independent origins, not pages; ties are broken by rank, never by
page count. A **gate** flags DATA_VOID when the top answer has fewer than two origins and CONTESTED when
the top two differ by at most one origin; either sets a hedge floor of at least "may", which is enforced
on the final answer. Guard reweights and annotates results; it never deletes them. All values were tuned on
dev only and frozen (`CONFIG_HASH 6646ef58...`). Extraction is rule-based (no model call); on dev pools, median latency
is 46 ms per query without embeddings and 790 ms with them on CPU.

## 5 Results

**Table 1. Preregistered hypotheses** (test split; 1,903 runs; Holm over the confirmatory family).

| ID | Hypothesis (pass threshold) | Estimate [95% CI] | Holm p | Result |
|---|---|---|---|---|
| H1 | Dose response: slope > 0 for all models; k50 <= 5 for >= 1 model | lowest k50 7.4 [5.4, 7.7] (gpt-oss; gflite31 7.2-8.1 by label) | <.001 (slope) | **FAIL** (k50 > 5) |
| H2 | Wire label buys pages: k50(wire)/k50(propaganda) > 1 | 0.89 [0.83, 0.97] (gflite31) | 1 | **FAIL** (reversed) |
| H3 | Data voids flip at lower dose: k50(void)/k50(known) < 1 | 0 [0, 0.23] (void k50 < 1 page) | .003 | **PASS** |
| G1 | Guard cuts flips >= 50% vs none at k = 5, 8 on T0 and T1 | T1 k = 5: -100% (6/27 vs 3/27 flips) | 1 | **FAIL** (only 1 cell run) |
| G2 | Guard flip >= 10 pts below prompt and page vote at k = 5 | -22 pts [-37, -7] vs prompt (T1) | 1 | **FAIL** |
| G3 | Clean drop <= 2 pts (TOST +/-3); syndication; false merges <= 5% | clean drop 0.0 pts (TOST passes) | .003 | incomplete (no agent-level syndication or merge logs) |
| G4 | Void k = 3: hedged/abstain among wrong answers +20 pts; over-hedge limits | +7 pts [0, 21]; single-origin over-hedge 100% | 1 | **FAIL** |
| H4, H4b | Hedge retention (arm D) | — | — | not run (quota) |
| H5 | Urdu flips more than English at k = 3 | Urdu 0/14 vs English 6/21 | — | **FAIL** (no Urdu flips; regression not estimable) |
| G6 | Guard's benefit falls from T0 to T4; < 50% on T4 | not informative at agent level (1 flip) | — | see decision-level results |

**Agents hedge before they flip on known facts; voids flip at once (Fig. 1).** On the 40 known facts
(gflite31, arm A), correct answers fell from 100% at k = 0 to 75%, 31%, 12% and 0% at k = 1, 2, 3 and 5.
Flips stayed rare until k = 8 (0.8% at k = 3, 3.3% at k = 5, 50.8% at k = 8); the rest of the answers hedged,
abstained or named both values (87.5% at k = 3). On data voids every answer flipped from the first
planted page (39/39 at each k >= 1), so k50(void) is below one page and H3 passes (Holm p = .003). The
fake-support-number brands sit in between: 38% flips at k = 5 and 48% at k = 8 (n = 21 each). Pooled over
regimes, planting 3 of 10 results flipped 23% of answers (42/180). The slope on dose was positive for both
models (p < .001), but the k50 for known facts was 7-8 pages, above the preregistered 5, so H1 fails.
GPT-OSS-120B (partial: 67 runs on 8 questions) never flipped at k = 3 and flipped 14 of 15 times at k = 8.

**A credibility label works backwards.** On known facts, planted pages labelled as wire copy flipped
twice as many answers as the same claim labelled as propaganda (70% vs 35% at k = 8, n = 40 each; blog
47.5%) and reached k50 sooner (7.2 vs 8.1 pages; ratio 0.89 [0.83, 0.97]). H2, which predicted that a reputable label buys extra pages, fails in the
reverse direction: the label made the attack cheaper.

**Guard at the decision level (frozen, held-out pages, 100 test questions).** Before any model reads the
results, Guard's own top answer is the planted one in 7% [3, 12] of T0 pools at k = 5, against 62% [53, 71]
for page vote (-55 pts [-65, -45]); at k = 8, 17% vs 75%. On independently paraphrased T1 campaigns it
barely helps: 69% vs 76% at k = 5 (-7 pts [-14, -1]) and 97% vs 100% at k = 8, because Guard counts a T1
campaign as 5.4 independent origins on average (T0: 1.0). This is the failure we preregistered for G1 and
G2 on T1. The cost is small where we expected it: clean decision accuracy is unchanged (97% for both),
syndicated copies always form one origin, and 1.8% [1.4, 2.3] of honest cross-domain page pairs are falsely
merged (G3's false-merge conjunct passes). The gate's price is over-hedging: every honest single-origin
fact is flagged (100%), so G4 fails by construction.

**Guard with the agent in the loop (gflite31, held-out pages; Fig. 2).** Guard did not reduce flips: at T1 k = 5
the agent flipped 47.5% of answers with Guard against 33% without (all regimes; 6/27 vs 3/27 on known
facts), so G1 and G2 fail. But Guard changed what the agent did with conflicting results. At k = 3 it
turned hedges into correct answers: 68% correct with Guard vs 31% without on T0 (page vote 62%, prompt
48%), and 53% vs 3% on T1. On data voids Guard did not stop flips (13 of 14 at k = 3), but it hedged 11 of
those 13, against 0 of 15 without a defence; because a hedged planted answer still counts as a flip, G4's
preregistered measure rose only 7 pts. Clean accuracy at k = 0 was 100% under every defence (G3 clean
conjunct passes), while every correct single-origin answer carried Guard's hedge.

**Figure 1** (`results/figures/fig_bench_dose.png`): flip rate vs planted pages, by label on known
facts and for data voids, per model; bands are Wilson 95% intervals. **Figure 2**
(`results/figures/fig1_hero.png`): agent flip rate by defence on held-out T1 pages, known facts.

**Urdu pilot (partial, unbalanced).** With 89 of 180 planned runs, Urdu answers flipped less than English
at k = 3 (0/14 vs 6/21) and at k = 8 (6/9 vs 15/22); with no Urdu flips at k = 3 the preregistered
regression is not estimable, and we draw no conclusion beyond "no evidence that Urdu is more vulnerable".

**Human validation.** The κ labelling of 50 dev-pilot runs by all three authors (PREREG §3) was not
finished by the v1 deadline; κ will be added in the final version, and if it falls below 0.6 we will
report it as a failed gate without changing the scorer.

## 6 Using Planted

`pip install -e .` provides `from planted.guard import guard, enforce`: `guard(question, results)` takes a
retriever's results (url plus title, snippet or content) and returns reweighted results, an origin count
per answer, warnings and a hedge floor; `enforce(answer, floor)` applies the floor. `planted serve`
exposes Guard and the mock web as a proxy for gpt-researcher's custom retriever. The Inspect task
`planted_bench` (`-T guard=true -T tier=T1`) is Register-ready (submission pending an arXiv URL). The
generator rebuilds both page banks from a seed, and `python -m analysis.analyze logs/` rebuilds Table 1
and every figure. A static scorecard (English/Urdu) shows the headline numbers for fact-checkers.

## 7 Discussion

**Grooming or voids? Both, through different failures.** On well-covered facts the agent rarely adopts
a planted answer until it is the majority; instead, a few planted pages are enough to destroy correct
answers, turning them into hedges or "sources disagree". On data voids a single planted page is accepted
every time. This is consistent with both audits: false claims dominate where coverage is thin (voids),
while on well-covered topics the visible symptom is lost answers rather than false ones. Our design shows
the two mechanisms side by side; it cannot say how often each occurs on the live web.

**Why counting origins only partly works.** Origin counting removes the copy-paste advantage almost
completely at the decision level, but independently paraphrased pages share nothing a provenance signal
can see: with our embedder, paraphrased campaign pages are as dissimilar as independent honest reports
(median answer-masked cosine 0.720 vs 0.735 on dev). This is Bara's ancestry problem in practice, and it
means that a campaign willing to pay for paraphrases defeats Guard. With an agent, Guard's main benefit
was different from the one we preregistered: it resolved conflicts in favour of the answer with more
independent origins (more correct answers at k = 3) and hedged void answers, but it also made the agent
commit when the paraphrased campaign looked like the majority, so flips did not fall.

**Costs.** Clean accuracy did not drop, and false merges were rare (1.8% of honest pairs). The price is the
gate: every fact with only one real source is hedged, which is defensible for support numbers and
breaking news but costly for obscure true facts.

**Limitations.** (1) Only 1,903 of about 23,100 planned runs were possible on free tiers: GPT-OSS is
partial, arm D (hedges) and part of arm G (T3, k = 8) were not run, and the Urdu pilot is unbalanced. Most
Guard hypotheses therefore rest on one model and 40 questions. (2) The web is synthetic; our rates bound
vulnerability, not prevalence. (3) The agent is single-call, not a multi-step browsing agent. (4) The rule
extractor scored 100% on dev but 82% on held-out English and 74% on held-out Urdu pages, so decision-level
Guard numbers carry extraction error. (5) κ is pending. (6) The firewall between data and defence is a
procedure, not a guarantee.

## 8 Conclusion

Three numbers: one planted page flips every answer to a question the web cannot otherwise answer; three
planted pages out of ten cut correct answers on well-covered facts from 100% to 12%; and counting
independent origins removes copy-paste campaigns (62% to 7% planted wins) but not paraphrased ones (76% to
69%). Our recommendation: search agents should check how many *independent* sources support an answer,
and refuse to answer with confidence when there is only one, while treating paraphrase-level campaigns as
an open problem that page-level signals cannot solve.

## Appendix A. Limitations and Dual-Use / Ethical Considerations

**Limitations.** See §7. In addition: attack pages were partly template-generated (the share per tier is
recorded per page); T4 adapts to a similarity model, not to Guard's full pipeline; hedge judgements are
coarse.

**Dual use.** The attacker tiers describe how to make planted claims harder to detect. We limit that
uplift: every domain is a fictional `.example` domain; no real outlet, person, brand or government body is
named or imitated; demo questions are non-political (fictional appliance brands, invented reservoirs);
the adaptive generator ships as code that needs the user's own model key, with no prebuilt evasive corpus
beyond what the evaluation needs; and the defence ships alongside the attack. The phenomenon (volume beats
source reliability) is already documented in deployed systems.

**Personal data and human subjects.** No personal data was collected; hand labels were produced by the
three authors; no human subjects. The Urdu set was checked by an author who is a native Urdu speaker.

**Preexisting code.** Code adapted from our earlier project "Refusal Routers" lives in `planted/engine/`
and is marked there as preexisting.

## Appendix B. Deviations from the preregistration

1. **Sizes and roster.** Free-tier keys only: 1,903 of about 23,100 planned runs. Gemini 2.5 Flash-Lite was
   unavailable to new keys; models run were Gemini 3.1 Flash-Lite and GPT-OSS-120B (partial, 67/180).
   Arm D (H4, H4b) and part of arm G (T3, T0/T1 at k = 8, the second Guard model) were not run; the Urdu
   pilot is partial (89/180).
2. **Question selection.** A regime-stratified seed-0 sample (60 = 40 known / 13 void / 7 support; arm G 40;
   Urdu 30) instead of all 100 test questions.
3. **Single-origin substitutions.** Void questions have no single-origin variant; 8 were replaced by
   known/support `-so` questions (listed in `docs/handoff_B.md`).
4. **Failed runs.** 13 arm-G and 91 Urdu runs failed after retries (authentication errors) and are excluded
   from denominators (PREREG §7).
5. **Offline Guard evaluation.** Decision-level, page vote as the comparison where PREREG names no
   defence; a supplementary T0 k = 5 cell (G1/G2 name T0 k = 5, arm G did not list it); k50 there uses
   linear interpolation.
6. **Extraction** generalised imperfectly (82.1% held-out English, 73.8% held-out Urdu).
7. **κ** labelling was not finished by the v1 deadline.
8. **Reporting fix after the tag:** a numpy boolean was printed as "incomplete" instead of FAIL in Table 1
   (G4); no definition changed.
