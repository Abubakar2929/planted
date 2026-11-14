# Handoff to A (from B, 2026-11-14)

C is unavailable. **A now writes Guard and the baselines** (`planted/guard/`, `planted/baselines/`):
A has never read the generator, so the human firewall still holds (generator by B, Guard by A).
**B now owns C's other work**: `PREREG.md`, `analysis/`, `site/`, Results/Discussion. B still never opens
`planted/guard/` or `planted/baselines/`; the analysis reads only Contract-2 logs.

## 1. Answers to the open questions in `docs/progress_A.md`

**Linking pages to questions, pools.** Please call B's pool builder instead of the engine's own rules:

```python
from data.pools import PageBank, build_pool          # data/README.md documents every rule
bank = PageBank.load("data/pages/main")             # Guard sweep (arm G, T4): PageBank.load("data/heldout/pages")
pages = build_pool(bank, question, condition)       # list[Page], always 10, all from different domains
```

It already handles everything the engine's rules miss: data voids (no honest page exists; fillers pad the
pool), support brands (one official page + fillers), single-origin (`qid` + `-so`) and syndication
(`qid` + `-syn`) variants that share the base fact's pages, Urdu questions (`qid` + `-ur`), arm D hedge
pools, and T3 cross-lingual campaigns (planted pages in **both** languages, by design). Pages are linked
to questions through `index.jsonl` (`qid, url, role, tier, label, slot, lang, hedge, gen`), so no `qid`
in the url is needed. Doses nest (the first k planted slots), and order is a seeded shuffle; the engine
may re-rank. `build_pool` is tested on every condition in the grid (`tests/test_data.py`).

- *Honest fill only correct pages?* Yes, for known facts (10 honest pages, all asserting the correct
  answer). For void / support / single-origin, the fill is fillers (pages about the entity that never
  state the fact): `build_pool` does this.
- *Arm D neutral filler, k = 0?* Arm D pools are `n_agree` hedge pages + fillers, and k = 0 (no planted pages).
- *T3 other-language planted pages?* Yes: a T3 campaign alternates EN and UR pages on purpose.
- *`open_url(episode_id, url)` vs the contract:* agreed that the engine needs the episode id. That is a
  contract question for an `[ALL]` commit; B is fine with it.

## 2. Model availability (blocking for the sweep)

On 2026-11-14 `gemini/gemini-2.5-flash-lite` returned **404 "no longer available to new users"** for a new
key. `gemini-3.1-flash-lite` works (with `temperature`); `gemini-3.5-flash-lite` works only **without**
`temperature`. Your alias `gflite` points at 2.5: please check it with your key and switch the Guard model 1
to an available model before the sweep. Record the final roster in `PREREG.md` §8 (item 2).
GPT-OSS on Groq's free tier: 1,000 requests/day, 8,000 tokens/min (measured from its `x-ratelimit` headers).

## 3. What the analysis needs from your logs and Guard tooling

- **Every run** as a Contract-2 `LogLine` in `logs/*.jsonl` (your `JsonlLogger`). The analysis re-scores
  each run from `final_answer`, `correct_answer`, `planted_answer`, `regime`, `lang` with the preregistered
  rules (`analysis/score.py`), and keeps your `outcome` for an agreement check. Please make `qid` the
  question's qid (including `-so` / `-syn` / `-ur` suffixes) and `regime` the question's regime.
- **Arms and conditions exactly as in `PREREG.md` §2** (arm G uses `data/heldout/pages`; label `None` there).
- **False merges (G3)**: write `logs/guard_merges.jsonl`, one line per page pair in each Guard episode:
  `{"episode_id", "url_a", "url_b", "same_cluster": bool, "both_honest": bool, "same_origin_truth": bool}`
  where `same_origin_truth` is true for two planted pages of one campaign or two syndicated copies
  (ground truth from the hidden `campaign_id` / the bank index, used for scoring only, never for tuning).
- **Real-web check**: `logs/realweb.jsonl` with your summary (false merges, over-hedge, $/query, p50/p95 latency).
- **Frozen Guard values** go in `PREREG.md` §6 (MinHash threshold, tau_strict, embedder, gate rule,
  extraction model and prompt hash), tuned on dev20 only, then tag `prereg-v2` **before** the main sweep.

Rebuild everything with `python -m analysis.analyze logs/` (tested on simulated logs in `tests/test_analysis.py`).
