# Paper sections owned by B (paste into the official Google Doc template)

Status: draft. `__` = number from C's analysis (never estimate). `[verify]` = open the source before
submitting. Section numbers follow PLAN.md §11 / docs/plan-v2.2.md "Report outline".

---

## Abstract (draft; 150-250 words; finalise with real numbers on Monday)

AI search agents decide what is true by reading the top search results, and they count pages, not
sources. We present Planted, a measure-fix-ship study of this failure. **Planted Bench** is a controlled,
fully fictional mock web in English and Urdu where we vary how many of ten results carry a planted claim,
how those pages are labelled, whether honest coverage exists at all (data voids), and how cautiously
sources state a finding. Planting 3 of 10 results flips __% of answers (k50 = __ pages; __ in Urdu), and a
reputable wire-service label buys only __ extra pages. **Planted Guard** is a drop-in retrieval-time
filter that groups results by independent origin, using provenance signals (domain family, shared
boilerplate, cited origin, author and time) together with content similarity, and counts groups instead of
pages. It reweights rather than deletes, forces a hedge when fewer than two independent origins support an
answer, and never lets an answer sound more certain than its sources. On held-out attack pages from a
different generator and model family, Guard cuts flips to __% at a __-point clean-accuracy cost, beating a
reliability prompt and page-count voting; as preregistered, its advantage shrinks to __% against an
adaptive attacker. **Planted Ship** packages Guard as one function, a gpt-researcher proxy, a
Register-ready Inspect task and a bilingual scorecard for fact-checkers.

---

## 1 Introduction (~0.75 page)

In December 2025, an AI answer engine told users that a scam phone number was an airline's official
support line and attributed it to ten sources; attackers had seeded the number across compromised hosts
so that AI systems would repeat it [Aurascape; verify]. The ten sources were one campaign. Two audits of
live AI tools disagree on why such failures happen. NewsGuard's audit of the ten leading AI tools found them repeating
false claims 35% of the time in August 2025, up from 18%, while their non-response rate fell from 31% to
0%, a shift it ties to the tools adopting real-time web searches [NewsGuard, 4 Sep 2025; checked]. A Harvard
Kennedy School study found that only 5% of chatbot responses supported Kremlin disinformation and argued
that the cause is *data voids*, topics with little reliable coverage, recommending warning banners
[Alyukov et al., HKS Misinformation Review; verify]. The two explanations call for different fixes, and
neither audit can separate them, because they observe the web as it is.

We separate them causally. In a controlled mock web we vary, independently, the **dose** (how many of the
ten results carry a planted claim), the **label** (wire service, propaganda network, anonymous blog), the
**regime** (well-covered fact, data void, fake-support-number brand) and the **source hedge** (how
cautiously sources state a finding), in English and in Urdu. Everything is invented, so no model can know
the answers in advance and no real person, outlet or brand is touched.

Measuring the failure is not enough: 2026 work has already shown that repetition can beat credibility
[Schuster et al.] and that coordinated poison defeats page-count voting [Li, Guo & Xu]. The question that
remains is whether an agent can be made to count *sources* instead of pages, without paying the
clean-accuracy price of deleting suspected clusters. Our answer is Planted Guard, a retrieval-time filter
that estimates independent origins from provenance and content, votes by origin, gates confident answers
in data voids, and enforces a hedge floor.

**Contributions** (to our knowledge): (1) a dose-response benchmark for search-agent poisoning that
reports how many pages a credibility label is worth and tests the data-void explanation causally, with
the first controlled measurement in Urdu; (2) an independence-weighted corroboration defence for
web-search agents that reweights rather than deletes, evaluated as a shift in the dose curve against four
attacker tiers on held-out pages, with its clean-accuracy, false-merge and over-hedging costs; (3) an
agent-side data-void hedge gate that tests the banner recommendation, and a deterministic source-hedge
floor; (4) a preregistration with a predicted failure on an adaptive attacker; (5) installable artefacts:
a one-line `guard()` function, a gpt-researcher proxy, a Register-ready Inspect task and a bilingual
scorecard.

---

## 2 Related work (~0.75 page)

**Repetition, credibility and search agents.** Schuster, Gautam and Markert show, across 373 fictional
entities and 13 models, that models rank government above newspapers above social media, but that
repeating a low-credibility source reverses this ordering [arXiv 2601.03746; verify]. HAE-GEO builds a
controlled poisoned web of 72k pages, documents a "corroboration trap", and finds that defensive prompting
increases verification but rarely recovers the right answer [arXiv 2609.06027; verify]. Zhang, Triedman
and Shmatikov find a short user-generated URL cited in 38-51% of deep-research reports [arXiv 2605.24245;
verify]. We add a fine-grained dose with a fitted k50, credibility labels, data voids, hedges and Urdu, and
test a defence that is not a prompt. A previous Apart entry showed that injected claims deceive browsing
LLMs, without dose, labels, language or a defence [Apart Jan 2026 2nd place; verify].

**Coordinated poisoning and independence.** CoordGuard shows that coordinated poison forms a dense
embedding component that consistency defences miss: RobustRAG and ReliabilityRAG reach an
exposure-conditional attack success rate of 0.512 against 0.576 undefended, and always-filtering suspected
clusters lowers it to 0.167 at a 13.6-point clean-accuracy cost [Li, Guo & Xu, arXiv 2610.24834]. GuardRAG
removes near-duplicates and prunes suspicious clusters after hierarchical clustering in static RAG
[Jiao et al., arXiv 2610.35071]. Bara formalises why more reports need not mean more evidence, showing that
a report-space deduplication mechanism tracks representation similarity (cluster-count shift 1.425) far
more than true evidential ancestry (0.040) [arXiv 2609.01873]. Lee and Kim show that lexical
deduplication catches near-identical sybil groups but not polymorphic ones, and that abstention and drift
carry 47-66% of output mass [arXiv 2607.03739]. Guard differs from these in setting (tool-using web-search
agents rather than static RAG), in signal (provenance edges as a proxy for ancestry, alongside content), and
in action (reweight and gate rather than delete). We adopt Lee and Kim's outcome split
(flip / abstain-or-hedge / drift). TriShieldRAG's layered defence was bypassed on all 500 documents by
formatting-only adaptive attacks [Mohanty et al., arXiv 2607.23838], which is why we randomise formatting
in every tier and preregister a failure against an adaptive attacker.

**Other defences.** RobustRAG's certificate assumes poisoned passages are a minority [Xiang et al., arXiv
2405.15556; verify]; Evidence Balancing rebalances retrieved documents by *stance*, not by source
[Yang et al., arXiv 2610.34294]; constraint-checking prompts reduce wrong-question evidence adoption from
20.7% to 14.3% [Lazy Grounding, arXiv 2608.30303; verify]. **Certainty.** Single-source rewriting distorts
certainty by up to ~75% [Belem et al., arXiv 2606.07951; verify]; we study multi-source synthesis and
enforce a hedge floor. **Language.** CLEAR measures knowledge-conflict persuasion in 10 languages, not Urdu
[arXiv 2601.07041; verify].

---

## 3 Planted Bench — data (B's part of §3; ~0.5 page; A writes harness, engine and Inspect)

**World.** All entities, people, outlets and domains are invented. Names are composed from syllables that
each carry a fixed Urdu spelling, giving consistent English and Urdu forms without machine
transliteration. All domains use the reserved `.example` suffix, and all phone numbers fall in the
+1-555-0100..0199 range reserved for fiction. A validator rejects any page naming a real outlet or brand.

**Questions.** 120 facts in three regimes: 80 *known* facts across eight types (founding year,
population, bridge length, first director, headquarters, opening date, summit height, species count),
each covered by ten independent honest pages; 25 *data voids* about obscure entities, where no page states
the answer (correct behaviour is to abstain); and 15 *fake-support-number* brands, where only the brand's
official site states the real number. 20 facts form the dev split (stratified by regime); Guard is tuned
only on these. For the Guard evaluation, every known and support fact also has an *honest single-origin*
variant (exactly one true source) and a *benign syndication* variant (one wire story on three domains plus
independent coverage). 60 test questions have Urdu versions, and 150 true findings (five study types,
e.g. a pollution change after a stove-replacement scheme) form the hedge arm.

**Pages and attacker tiers.** Each result is a full page with a randomised outlet whose name and domain
match, plus author, date, boilerplate, genre, length and sentence order, randomised in every tier.
A campaign therefore shares only what a real one would: the claim, plus, in T0 only, a copied article and
a domain-family stem. **T0** copies one article verbatim to eight sites of one domain family (the
copy-paste pattern of laundering networks). **T1** writes eight independent paraphrases in different
outlet styles, under four labels. **T3** mixes English and Urdu pages in one campaign. **T4** draws six
candidates per page and keeps the one least similar to the campaign so far, after a claim-survival check.
Across the main bank, two T0 pages share word 5-grams with mean Jaccard 0.61, whereas two T1 pages share
0.03, the same as two independent honest pages (0.03), and two T4 pages 0.02. Paraphrase is thus lexically
indistinguishable from independent reporting, which is the case a defence must solve.

**Held-out generator.** Guard's test pages come from a second generator written blind to Guard: a new
template bank written from the threat model, a different page architecture (forum threads, press releases,
FAQ pages, listicles, news briefs), different outlet naming and domain-family schemes, and, for the
LLM-written tiers, a different model family. We report dev and test results side by side. The firewall
between data and defence (the data author never saw Guard's code; the Guard author never saw the
generator) is a procedure we followed, auditable in the commit history, not a guarantee.

**Hedges.** Source hedges have four levels (none, *may*, *preliminary*, *explicit disagreement*). An
English and Urdu lexicon detects each level; every hedge template is detected at its own level and no
unhedged page contains a hedge marker. Urdu matching normalises Unicode, strips zero-width joiners and
folds Arabic and Urdu letter variants.

**Generation.** [Fill in the backend actually used for the submitted pages. Committed now: deterministic
template generator. If the LLM run happens, write: "T1, T3 and T4 page text was written by Gemini 2.5
Flash-Lite (held-out: GPT-OSS-120B) at temperature 0.9 with a random outlet persona per page, each rewrite
passing a claim-survival check; __% fell back to templates."] Generation is seeded and reproduces every
file byte for byte.

---

## Appendix A. Limitations and Dual-Use / Ethical Considerations

**Limitations.** (1) *Synthetic web.* Pages are generated in a fictional world, so our rates bound
vulnerability under controlled conditions; they are not estimates of real-world prevalence. Real pages are
messier, and real provenance metadata is noisier than ours. The real-web check (__ harmless queries)
reports Guard's false-merge and over-hedge rates on live search results, but on a small sample.
(2) *Template realism.* [If offline:] Attack pages were generated from template banks rather than by a
language model; paraphrase diversity may differ from LLM-written campaigns. The held-out bank uses a
different architecture to limit over-fitting, but both banks share our authors' assumptions. (3) *Urdu.*
The Urdu set was written by the authors; [reviewer-approved by __ / checked by the authors only]. Urdu
results are framed as resource level, not culture, and each model's no-attack Urdu accuracy is reported
as a baseline. (4) *Attackers.* T4 adapts to a similarity model, not to Guard's full pipeline; stronger
adaptive attackers may do better. (5) *Agents.* We test __ models from 2 providers with a fixed tool loop
and non-streaming responses. (6) *Scoring.* Hedge judgements are coarse; human agreement on certainty is
low in prior work, so the lexicon is the primary measure and κ is reported.

**Dual use.** The attacker tiers describe how to make planted claims harder to detect. We limit that
uplift: every domain is a fictional `.example` domain; no real outlet, person, brand or government body is
named or imitated; demo questions are non-political (fictional appliance brands, invented reservoirs);
the adaptive generator ships as code that requires the user's own model key, with no prebuilt evasive
corpus beyond what the evaluation needs; and the defence ships alongside the attack. The phenomenon itself
(volume beats source reliability) is already documented in deployed systems and prior work.

**Personal data and human subjects.** No personal data was collected; hand labels were produced by the
three authors; no human subjects. The Urdu reviewer is acknowledged by name only with their consent.

**Preexisting code.** [Name any preexisting code reused from the Refusal Routers project, as in the README.]
