# Novelty notes (owner: B)

Checked 2026-11-14 by opening each arXiv abstract page (and the HTML full text for CoordGuard, Bara and
Lee & Kim). Numbers below are from those pages; anything not confirmed there is marked. Re-open each PDF
before the final reference check (PLAN.md Phase 5): fabricated or misstated references are disqualifying.

## The three defences the plan had not opened

| Paper | What it is | Overlap with Planted Guard | Verdict |
|---|---|---|---|
| **GuardRAG** (Jiao et al., arXiv 2610.35071, 26 Oct 2026) "A Post-Retrieval Defense against Poisoning Attacks in RAG" | Training-free post-retrieval filter: expand retrieval, remove near-duplicates, cluster with hierarchical agglomerative clustering (query-adaptive threshold), then **score and prune** suspicious clusters by relevance, size and compactness. 3 QA datasets, 6 LLMs. No ASR numbers in the abstract. | Clusters documents, like Guard. | **Differs:** static RAG, content-only clustering, and it *prunes* clusters. Guard runs on web-search agents, adds provenance edges (domain family, boilerplate, cited origin, author/time), *reweights instead of deleting*, and adds the data-void gate and hedge floor. Cite as the closest clustering defence. |
| **Evidence Balancing** (Yang et al., arXiv 2610.34294, 25 Oct 2026) "Factual Yet One-Sided: Stance Poisoning and Evidence Balancing in RAG" | Middleware between retriever and generator against *stance* skew from correct but one-sided documents (ProCon). Fixed balancing of **2 supporting + 2 opposing + 1 neutral** documents by stance label, plus a debiasing prompt. Stance deviation falls by 0.106-0.350; 6 of 8 settings significant after Holm. | Also middleware, also "rebalances" what the generator sees. | **Differs:** balances by *stance*, not by *source*; it never estimates source independence and targets one-sided truth, not false claims. No overlap with "count independent origins". |
| **TriShieldRAG** (Mohanty et al., arXiv 2607.23838, v2 26 Aug 2026) "3 Rings, One Blind Spot in Layered Defenses for RAG" | Ingest guard + retrieval scorer + 3-model consensus. Non-adaptive PoisonedRAG ASR 79% -> 1% on full NQ; **formatting-only adaptive attacks bypass the ingest guard on all 500 documents** and the other layers then help little; cross-model agreement 0.96 while ASR approaches 99%. The v1 headline result is withdrawn. | Layered defence evaluated against adaptive attackers. | **Supports our design:** it is direct evidence that defences must be tested on adaptive tiers, which is why we preregister a predicted failure on T4 (G6). Cite in Related Work and Discussion. |

**Conclusion:** none of the three is an agent-side, provenance-plus-content independence estimator that
reweights web-search results and adds a data-void gate and hedge floor. The plan's novelty claim stands,
with "to our knowledge". Do **not** claim the first clustering or anti-Sybil defence.

## Numbers to use in Related Work (verified on the papers)

- **CoordGuard** (Li, Guo & Xu, arXiv 2610.24834; title "Consistency Is the Attack Surface: Detecting
  Coordinated Retrieval Poisoning with Embedding Geometry"). Exposure-conditional ASR: undefended 0.576,
  RobustRAG/ReliabilityRAG 0.512, CoordGuard e5 always-filter **0.167**, at a **13.6-point clean-accuracy
  cost**; clean accuracy also falls from 0.328 to 0.216 under RobustRAG/ReliabilityRAG. A Contriever gate
  keeps clean accuracy at 0.315 with ASR 0.331. *Wording:* write "exposure-conditional ASR"; the paper does
  not say RobustRAG "only" reaches 0.512 (that gloss is ours, drop it).
- **Bara** (arXiv 2609.01873, "Epistemic Sybil Resistance: Multiplying AI Agents Without Multiplying
  Evidence"). Report multiplicity 1->32 collapses posterior coverage 0.940->0.263. A manipulation of
  *representation similarity* shifts a dedup mechanism's inferred cluster count by **1.425** (95% CI 1.363-1.485),
  while a fourfold change in true ancestry shifts it by **0.040**. *Wording:* say "representation
  similarity", not "wording". The m_eff = m / [1 + rho(m-1)] discount is **not in the abstract**: the paper
  cites it as prior work (Kish design effect) and shows when it is exact. Attribute it accordingly.
  Bara is about multi-agent aggregation on synthetic documents, not a RAG defence.
- **Lee & Kim** (arXiv 2607.03739, "A Failure-Mode Benchmark for Polymorphic Sybil Poisoning in RAG").
  Token-Jaccard >= 0.60 dedup catches **100% of monomorphic** (near-identical, mean Jaccard ~1.00) groups and
  **0% of polymorphic** ones (Sec. 3.3, Table 1). E5 >= 0.95 has a 9x false-positive rate (0.2% -> 1.8%).
  The abstract and Sec. 3.3 text give E5's polymorphic catch rate as **14.2%**, but Table 1 lists 85.8% for
  the same cell (100 - 85.8 = 14.2): the paper is internally inconsistent; quote 14.2% with "as reported in
  the text" or avoid the number. Abstention + drift hold **47-66%** of output mass (Sec. 7: 47.4-65.9%).
  *Wording:* "near-identical (monomorphic)", not "verbatim".

## How our data maps onto these papers

- Our **T0** (copy-paste) corresponds to Lee & Kim's monomorphic groups; our **T1/T4** to polymorphic ones.
  Our measured overlap matches their premise: T0 pages share word-5-grams heavily (main bank mean Jaccard
  0.61), T1 pages do not (0.03, the same as independent honest pages), so lexical dedup alone cannot see T1
  (see `data/README.md`).
- Bara's result (similarity is not ancestry) is why Guard needs **provenance** edges, and why the paper
  reports the **Guard - provenance** ablation next to full Guard.
- TriShieldRAG's formatting-only bypass is why our generator randomises boilerplate, layout and outlet
  chrome in **every** tier, and why the held-out bank uses a different page architecture.
