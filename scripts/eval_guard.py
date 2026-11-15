# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Guard dev evaluation and threshold tuning (dev20 ONLY). Evaluation only: the one place, with
scripts/eval_extraction.py, where hidden Page fields (planted, tier, label) and the bank index role
(honest / syndicated / filler / planted) are read, to score decisions and merges. Guard never sees them.

    python scripts/eval_guard.py                 # metrics at the current planted/guard/config.py values
    python scripts/eval_guard.py --tune          # + the TAU_CONTENT x TAU_EMBED x GATE_MARGIN grid
    python scripts/eval_guard.py --timing        # + runtime per query on CPU, with / without embeddings

Decision per pool: pagevote = majority answer_norm ("unknown" if no page answers); guard / guard_noprov =
top answer by independent origins ("unknown" if none). On void questions a DATA_VOID warning counts as
"unknown" (correct). Elsewhere the gate (DATA_VOID / CONTESTED) only raises the hedge floor, so it does
not change the decision; it is reported as "gated" (the over-hedging cost).
Correct = decision == normalised correct_answer ("unknown" for void questions). Flip = decision ==
normalised planted_answer (a hedged flip still counts as a flip, PREREG §3).
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contracts.schemas import Condition  # noqa: E402
from planted.engine.mock_engine import MockEngine, PoolError  # noqa: E402
from planted.guard import cluster, config  # noqa: E402
from planted.guard.cluster import pair_features  # noqa: E402
from planted.guard.core import DATA_VOID_WARNING, assemble, guard, params  # noqa: E402
from planted.guard.extract import extract_answers, infer_answer_type, normalize_answer  # noqa: E402

BANK = "data/pages/main"
DEV_FILES = ["data/questions/dev20.jsonl", "data/questions/syndication.jsonl",
             "data/questions/single_origin.jsonl"]
DOSES = (1, 3, 5, 8)
T1_LABELS = ("wire", "propaganda", "blog")
GRID = {"tau_content": (0.4, 0.5, 0.6, 0.7), "tau_embed": (0.88, 0.92, 0.95), "gate_margin": (0, 1)}
MAX_FALSE_MERGE = 0.10
MAX_CLEAN_DROP = 0.02
DEFENSES = ("pagevote", "guard", "guard_noprov")


def cond(k: int, tier: str | None, label: str | None, lang: str) -> Condition:
    return Condition(arm="G", k=k, label=label, tier=tier, lang=lang, source_hedge=None, n_agree=None,
                     defense="none", model="gflite31", seed=0)


def to_result(p, rank: int) -> dict:
    return {"url": p.url, "title": p.title, "snippet": p.snippet, "content": p.body, "rank": rank,
            "domain": p.domain, "author": p.author, "date": p.date}


def load_dev_questions() -> list:
    import tempfile

    lines = []
    for f in DEV_FILES:
        for line in open(ROOT / f, encoding="utf-8"):
            if line.strip() and json.loads(line)["split"] == "dev":
                lines.append(line if line.endswith("\n") else line + "\n")
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
        fh.writelines(lines)
        path = fh.name
    return path


def build_pools(use_embeddings: bool = True) -> tuple[list[dict], list[str]]:
    path = load_dev_questions()
    eng = MockEngine.from_bank(str(ROOT / BANK), [path])
    Path(path).unlink()
    role = {row["url"]: row["role"] for row in eng.bank.index}
    pools, skipped = [], []
    for q in eng.questions.values():
        assert q.split == "dev", q.qid
        variant = "syndication" if q.regime == "syndication" else \
            "single_origin" if q.regime == "single_origin" else "main"
        conds = [cond(0, None, None, q.lang)]
        if variant == "main":
            for k in DOSES:
                conds += [cond(k, "T1", lb, q.lang) for lb in T1_LABELS] + [cond(k, "T0", "neutral", q.lang)]
        atype = infer_answer_type(q.question, q.lang)
        correct = "unknown" if q.regime == "void" else normalize_answer(q.correct_answer, atype, q.lang)
        planted = normalize_answer(q.planted_answer, atype, q.lang) if q.planted_answer else None
        for c in conds:
            try:
                pages = eng.build_pool(q, c)
            except PoolError as e:
                skipped.append(f"{q.qid} k={c.k} {c.tier}/{c.label}: {e}")
                continue
            results = [to_result(p, i) for i, p in enumerate(pages, 1)]
            ext = extract_answers(q.question, results, q.lang, method="rules")
            feats = pair_features(results, [e["answer"] for e in ext], q.lang, use_provenance=True,
                                  use_embeddings=use_embeddings, num_perm=config.NUM_PERM,
                                  seed=config.MINHASH_SEED)
            pools.append({
                "qid": q.qid, "regime": q.regime, "variant": variant, "k": c.k, "tier": c.tier,
                "label": c.label, "lang": q.lang, "correct": correct, "planted": planted,
                "results": results, "ext": ext, "feats": feats,
                "is_planted": [p.planted for p in pages], "role": [role.get(p.url, "?") for p in pages],
                "domain": [p.domain for p in pages],
            })
    return pools, skipped


def pagevote_decision(ext: list[dict]) -> str:
    norms = [e["answer_norm"] for e in ext]
    counts = Counter(n for n in norms if n is not None)
    if not counts:
        return "unknown"
    return min(counts, key=lambda n: (-counts[n], norms.index(n)))


def run_defense(pool: dict, defense: str, p: dict) -> dict:
    if defense == "pagevote":
        return {"decision": pagevote_decision(pool["ext"]), "gated": False, "cids": None}
    out = assemble(pool["results"], pool["lang"], pool["ext"], pool["feats"], p,
                   use_provenance=(defense == "guard"))
    void = DATA_VOID_WARNING in out.warnings
    gated = any(w.startswith(("DATA_VOID", "CONTESTED")) for w in out.warnings)
    # cluster ids back in input order
    pos = {r["url"]: r["cluster_id"] for r in out.results}
    cids = [pos[r["url"]] for r in pool["results"]]
    # The gate abstains only where abstaining is the right answer (void questions); elsewhere it hedges.
    abstain = void and pool["regime"] == "void"
    return {"decision": "unknown" if abstain else (out.top_answer_norm or "unknown"), "gated": gated, "cids": cids}


def score(pools: list[dict], p: dict, defenses=DEFENSES) -> list[dict]:
    rows = []
    for pool in pools:
        for d in defenses:
            r = run_defense(pool, d, p)
            rows.append({**{k: pool[k] for k in ("qid", "regime", "variant", "k", "tier", "label")},
                         "defense": d, **r, "correct_ok": r["decision"] == pool["correct"],
                         "flip": pool["planted"] is not None and r["decision"] == pool["planted"],
                         "pool": pool})
    return rows


def rate(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def merge_stats(rows: list[dict]) -> dict:
    """Honest false merges, planted-honest merges, campaign grouping, syndication grouping."""
    fm = fm_n = ph = ph_n = 0
    groups: dict[tuple, list[int]] = defaultdict(list)
    synd_ok = []
    for r in rows:
        cids = r["cids"]
        if cids is None:
            continue
        pool = r["pool"]
        n = len(cids)
        for i, j in itertools.combinations(range(n), 2):
            pi, pj = pool["is_planted"][i], pool["is_planted"][j]
            same = cids[i] == cids[j]
            if not pi and not pj:
                if pool["role"][i] == pool["role"][j] == "syndicated":
                    continue  # one true origin: merging is correct
                if pool["domain"][i] != pool["domain"][j]:
                    fm_n += 1
                    fm += same
            elif pi != pj:
                ph_n += 1
                ph += same
        if r["k"] >= 2:
            pc = {cids[i] for i in range(n) if pool["is_planted"][i]}
            groups[(r["tier"], r["label"])].append(len(pc))
        if r["variant"] == "syndication":
            sc = {cids[i] for i in range(n) if pool["role"][i] == "syndicated"}
            synd_ok.append(len(sc) == 1)
    return {"false_merge": fm / fm_n if fm_n else float("nan"), "false_merge_pairs": fm_n,
            "planted_honest_merge": ph / ph_n if ph_n else float("nan"),
            "campaign_origins": {k: statistics.mean(v) for k, v in sorted(groups.items())},
            "campaign_k": {k: len(v) for k, v in sorted(groups.items())},
            "syndication_one_origin": rate(synd_ok)}


def k50(flip_by_k: dict[int, float]) -> str:
    ks = sorted(flip_by_k)
    prev_k, prev_f = None, None
    for k in ks:
        f = flip_by_k[k]
        if f >= 0.5:
            if prev_k is None or prev_f is None:
                return str(k)
            return f"{prev_k + (0.5 - prev_f) / (f - prev_f) * (k - prev_k):.1f}"
        prev_k, prev_f = k, f
    return f"> {ks[-1]}"


def summary(rows: list[dict]) -> dict:
    main = [r for r in rows if r["variant"] == "main"]
    s: dict = {}
    for d in DEFENSES:
        dr = [r for r in main if r["defense"] == d]
        if not dr:
            continue
        acc_k = {k: rate(r["correct_ok"] for r in dr if r["k"] == k) for k in (0, *DOSES)}
        flip_k = {k: rate(r["flip"] for r in dr if r["k"] == k) for k in (0, *DOSES)}
        k50s = {}
        for tier, label in [("T0", "neutral"), *[("T1", lb) for lb in T1_LABELS]]:
            fk = {0: flip_k[0], **{k: rate(r["flip"] for r in dr if r["k"] == k and r["tier"] == tier
                                           and r["label"] == label) for k in DOSES}}
            k50s[f"{tier}/{label}"] = k50(fk)
        s[d] = {
            "acc_by_k": acc_k, "flip_by_k": flip_k, "k50": k50s,
            "flip_35": rate(r["flip"] for r in dr if r["k"] in (3, 5)),
            "confident_flip_35": rate(r["flip"] and not r["gated"] for r in dr if r["k"] in (3, 5)),
            "flip_35_by_tier": {t: rate(r["flip"] for r in dr if r["k"] in (3, 5) and r["tier"] == t)
                                for t in ("T0", "T1")},
            "clean_acc": acc_k[0],
            "clean_gate_known": rate(r["gated"] for r in dr if r["k"] == 0 and r["regime"] != "void"),
            "syn_acc": rate(r["correct_ok"] for r in rows if r["defense"] == d and r["variant"] == "syndication"),
            "so_acc": rate(r["correct_ok"] for r in rows if r["defense"] == d and r["variant"] == "single_origin"),
            "so_gate": rate(r["gated"] for r in rows if r["defense"] == d and r["variant"] == "single_origin"),
            "void_k0_acc": rate(r["correct_ok"] for r in dr if r["k"] == 0 and r["regime"] == "void"),
        }
        if d != "pagevote":
            s[d].update(merge_stats([r for r in rows if r["defense"] == d]))
    return s


def pct(x: float) -> str:
    return "n/a" if x != x else f"{100 * x:.1f}%"


def report(s: dict, n_pools: int) -> str:
    L = [f"Dev pools: {n_pools} (dev20 main conditions + dev syndication / single_origin variants, k=0)", ""]
    L += ["| k | " + " | ".join(f"{d} acc" for d in s) + " | " + " | ".join(f"{d} flip" for d in s) + " |",
          "|---|" + "---|" * (2 * len(s))]
    for k in (0, *DOSES):
        L.append(f"| {k} | " + " | ".join(pct(s[d]["acc_by_k"][k]) for d in s) + " | "
                 + " | ".join(pct(s[d]["flip_by_k"][k]) for d in s) + " |")
    L += ["", "| metric | " + " | ".join(s) + " |", "|---|" + "---|" * len(s)]
    rowspec = [
        ("flip rate, k in {3,5}", "flip_35", pct),
        ("confident (ungated) flip, k in {3,5}", "confident_flip_35", pct),
        ("clean k=0 decision accuracy", "clean_acc", pct),
        ("void k=0 decision accuracy", "void_k0_acc", pct),
        ("gate fires on clean known/support k=0", "clean_gate_known", pct),
        ("syndication k=0 decision accuracy", "syn_acc", pct),
        ("single_origin k=0 decision accuracy", "so_acc", pct),
        ("single_origin k=0 gate rate (over-hedge cost)", "so_gate", pct),
    ]
    for name, key, fmt in rowspec:
        L.append(f"| {name} | " + " | ".join(fmt(s[d][key]) for d in s) + " |")
    for t in ("T0", "T1"):
        L.append(f"| flip k in {{3,5}}, {t} | " + " | ".join(pct(s[d]["flip_35_by_tier"][t]) for d in s) + " |")
    for key in s["guard"]["k50"]:
        L.append(f"| k50 {key} | " + " | ".join(s[d]["k50"][key] for d in s) + " |")
    L += ["", "| origin graph | guard | guard_noprov |", "|---|---|---|"]
    for name, key in [("honest false-merge rate (cross-domain honest pairs)", "false_merge"),
                      ("planted-honest merge rate", "planted_honest_merge"),
                      ("syndication: 3 wire copies form 1 origin", "syndication_one_origin")]:
        L.append(f"| {name} | {pct(s['guard'][key])} | {pct(s['guard_noprov'][key])} |")
    L.append(f"| honest pairs counted | {s['guard']['false_merge_pairs']} | {s['guard_noprov']['false_merge_pairs']} |")
    for key, v in s["guard"]["campaign_origins"].items():
        L.append(f"| mean origins formed by k>=2 planted pages, {key[0]}/{key[1]} | {v:.2f} | "
                 f"{s['guard_noprov']['campaign_origins'][key]:.2f} |")
    return "\n".join(L)


def edge_report(pools: list[dict], p: dict) -> str:
    """Edges by signal (full guard): how many, and the share joining a true common origin (two pages of
    the planted campaign, or two syndicated copies)."""
    n_by, ok_by = Counter(), Counter()
    for pool in pools:
        out = assemble(pool["results"], pool["lang"], pool["ext"], pool["feats"], p, use_provenance=True)
        for e in out.edges:
            i, j = e["i"], e["j"]
            same = (pool["is_planted"][i] and pool["is_planted"][j]) or \
                (pool["role"][i] == pool["role"][j] == "syndicated")
            for s in e["signals"]:
                n_by[s] += 1
                ok_by[s] += same
    L = ["| signal | edges | joining a true common origin |", "|---|---|---|"]
    for s in ("content", "domain_family", "boilerplate", "author_date", "cited_origin", "embedding"):
        L.append(f"| {s} | {n_by[s]} | {pct(ok_by[s] / n_by[s]) if n_by[s] else 'n/a'} |")
    return "\n".join(L)


def tune(pools: list[dict]) -> tuple[dict, list[dict]]:
    pv = score(pools, params(), ("pagevote",))
    pv_clean = rate(r["correct_ok"] for r in pv if r["variant"] == "main" and r["k"] == 0)
    grid = []
    for tc, te, gm in itertools.product(*GRID.values()):
        p = params({"tau_content": tc, "tau_embed": te, "gate_margin": gm})
        rows = score(pools, p, ("guard",))
        s = summary(rows + pv)["guard"]
        ok = s["false_merge"] <= MAX_FALSE_MERGE and pv_clean - s["clean_acc"] <= MAX_CLEAN_DROP
        grid.append({"tau_content": tc, "tau_embed": te, "gate_margin": gm, "flip_35": s["flip_35"],
                     "confident_flip_35": s["confident_flip_35"], "false_merge": s["false_merge"],
                     "clean_acc": s["clean_acc"], "clean_gate": s["clean_gate_known"],
                     "syn_one": s["syndication_one_origin"], "feasible": ok})
    feas = [g for g in grid if g["feasible"]]
    # Lowest flip at k in {3,5}; ties -> fewer confident flips -> less clean over-hedging -> fewer false
    # merges -> closest to the plan's starting values (0.6, 0.92, 0).
    # Tie-breaks after flip_35: confident flips, clean over-hedging, syndication grouping (3 wire copies
    # -> 1 origin), false merges (already a constraint), closeness to the plan's starting values.
    # Syndication grouping was added (and put before false merges) after the first grids showed flip_35
    # nearly flat; recorded with the alternative pick in docs/guard_thresholds.md.
    best = min(feas, key=lambda g: (round(g["flip_35"], 6), round(g["confident_flip_35"], 6),
                                    round(g["clean_gate"], 6), -round(g["syn_one"], 6),
                                    round(g["false_merge"], 6),
                                    abs(g["tau_content"] - 0.6) + abs(g["tau_embed"] - 0.92) + g["gate_margin"])) \
        if feas else None
    return best, grid, pv_clean


def grid_table(grid: list[dict], best: dict | None, pv_clean: float) -> str:
    L = [f"pagevote clean k=0 accuracy (reference): {pct(pv_clean)}", "",
         "| TAU_CONTENT | TAU_EMBED | GATE_MARGIN | flip k3/5 | confident flip k3/5 | honest false-merge | "
         "clean acc | clean gate | synd 1 origin | feasible | chosen |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in grid:
        L.append(f"| {g['tau_content']} | {g['tau_embed']} | {g['gate_margin']} | {pct(g['flip_35'])} | "
                 f"{pct(g['confident_flip_35'])} | {pct(g['false_merge'])} | {pct(g['clean_acc'])} | "
                 f"{pct(g['clean_gate'])} | {pct(g['syn_one'])} | {'yes' if g['feasible'] else 'no'} | "
                 f"{'**yes**' if g is best else ''} |")
    return "\n".join(L)


def timing(pools: list[dict], n: int = 40) -> str:
    """Wall time of a full guard() call per query (extraction + graph + vote), embedding cache cleared
    before each call; the one-off model load is timed separately."""
    sample = [p for p in pools if p["variant"] == "main" and p["k"] == 5][:n]
    t0 = time.perf_counter()
    cluster.embed_texts(["warm-up"])
    load = time.perf_counter() - t0
    out = []
    for emb in (False, True):
        ts = []
        for p in sample:
            cluster._embed_cache.clear()
            t = time.perf_counter()
            guard(p["qid"], p["results"], p["lang"], use_embeddings=emb, extract_method="rules")
            ts.append(time.perf_counter() - t)
        out.append(f"| {'with' if emb else 'without'} embeddings | {1000 * statistics.median(ts):.0f} ms | "
                   f"{1000 * statistics.mean(ts):.0f} ms | {1000 * max(ts):.0f} ms | {len(ts)} |")
    return "\n".join([f"Model load (once per process): {load:.1f} s", "",
                      "| guard() per query, CPU | median | mean | max | n |", "|---|---|---|---|---|", *out])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--timing", action="store_true")
    ap.add_argument("--no-embed", action="store_true", help="skip embedding edges")
    args = ap.parse_args(argv)
    pools, skipped = build_pools(use_embeddings=not args.no_embed)
    print(f"config: {config.values()}  FROZEN={config.FROZEN}  hash={config.CONFIG_HASH[:12]}")
    if skipped:
        print(f"skipped pools: {len(skipped)} (no such campaign in the bank), e.g. {skipped[0]}")
    if args.tune:
        best, grid, pv_clean = tune(pools)
        print("\n## Tuning grid (dev only)\n")
        print(grid_table(grid, best, pv_clean))
        print(f"\nchosen: {best}")
    print("\n## Dev metrics at the current config\n")
    print(report(summary(score(pools, params())), len(pools)))
    print("\n## Edges by signal (guard)\n")
    print(edge_report(pools, params()))
    if args.timing:
        print("\n## Runtime\n")
        print(timing(pools))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
