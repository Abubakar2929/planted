# OWNER: C (written by B after C became unavailable; see PREREG.md §8)
"""Hand labelling and agreement (κ) for the automatic scorer (PREREG §3; Gate 2: flip κ >= 0.6).

    python -m analysis.kappa sample logs/ --out labels/          # write the labelling sheets
    (each author fills labels/flip_<A|B|C>.csv and labels/hedge_<A|B|C>.csv, see labels/README.md)
    python -m analysis.kappa score labels/                       # -> labels/kappa.json

Two labelling sets, the same items for every labeller (so human-human agreement can be measured):
  flip set   50 runs where a flip was possible, flips first: half are runs the scorer called `flip` (all of
             them if fewer), the rest a random sample of the remaining runs (which may hold more flips);
             label one of correct / flip / abstain_hedge / drift.
  hedge set  arm D runs, 100 English + 50 Urdu, stratified by the lexicon's level; label the answer's
             certainty as none / hedged / disagree (coarse levels: human agreement on fine certainty
             levels is low, Belem et al.).
Sheets never show the scorer's label, the arm, the dose or the defence. The scorer's labels are kept in
labels/key.json. `score` reports human-human agreement (Fleiss' κ, all labellers) and human-scorer
agreement (Cohen's κ, majority human label vs the scorer), for flip (binary and 4-class) and per language
for hedges. **Gate 2 uses binary flip κ between the human majority and the scorer, >= 0.6**; hedge κ is
reported, never gated.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTCOMES = ["correct", "flip", "abstain_hedge", "drift"]
HEDGES = ["none", "hedged", "disagree"]
GATE = 0.6
COARSE = {"none": "none", None: "none", "may": "hedged", "preliminary": "hedged", "disagree": "disagree"}


# ---------------------------------------------------------------------------- agreement statistics
def cohen_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's κ for two raters over the same items."""
    n = len(a)
    if n == 0:
        return math.nan
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in cats) / n ** 2
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def fleiss_kappa(ratings: list[list[str]]) -> float:
    """Fleiss' κ; ratings[i] = the labels all raters gave item i (same number of raters per item)."""
    if not ratings or len(ratings[0]) < 2:
        return math.nan
    cats = sorted({x for r in ratings for x in r})
    m = len(ratings[0])
    counts = np.array([[r.count(c) for c in cats] for r in ratings], dtype=float)
    p_i = ((counts ** 2).sum(1) - m) / (m * (m - 1))
    p_j = counts.sum(0) / counts.sum()
    pe = float((p_j ** 2).sum())
    return 1.0 if pe == 1 else (float(p_i.mean()) - pe) / (1 - pe)


def majority(labels: list[str]) -> str:
    """Most common label; ties go to the first label in sorted order (deterministic)."""
    c = Counter(labels)
    top = max(c.values())
    return sorted(k for k, v in c.items() if v == top)[0]


# ---------------------------------------------------------------------------- sampling
def _question_texts() -> dict[str, str]:
    from data.pools import load_questions

    out = {}
    for f in sorted((ROOT / "data" / "questions").glob("*.jsonl")):
        out.update({q.qid: q.question for q in load_questions(f)})
    return out


def _pick_flip(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    d = df[df["planted_answer"].notna() & (df["k"] > 0)]
    flips = d[d["outcome"] == "flip"]
    n_f = min(len(flips), n // 2)
    a = flips.sample(n_f, random_state=seed) if n_f else flips.iloc[:0]
    rest = d.drop(a.index)
    b = rest.sample(min(len(rest), n - n_f), random_state=seed) if len(rest) else rest
    return pd.concat([a, b]).sample(frac=1, random_state=seed)  # shuffled: flips are not all at the top


def _pick_hedge(df: pd.DataFrame, lang: str, n: int, seed: int) -> pd.DataFrame:
    d = df[(df["arm"] == "D") & (df["lang"] == lang)].assign(_h=lambda x: x["answer_hedge"].map(COARSE))
    if d.empty:
        return d
    per = max(1, n // max(1, d["_h"].nunique()))
    parts = [g.sample(min(len(g), per), random_state=seed) for _, g in d.groupby("_h")]
    got = pd.concat(parts)
    if len(got) < n:  # top up from whatever is left
        rest = d.drop(got.index)
        got = pd.concat([got, rest.sample(min(len(rest), n - len(got)), random_state=seed)])
    return got.head(n).sample(frac=1, random_state=seed)


def sample(logs_dir: Path, out: Path, labellers: list[str], n_flip: int = 50, n_hedge_en: int = 100,
           n_hedge_ur: int = 50, seed: int = 0) -> dict:
    from analysis.analyze import load_logs

    df = load_logs(logs_dir, split=None)  # the pilot runs on dev questions
    if df.empty:
        raise SystemExit(f"no valid log lines under {logs_dir}")
    qtext = _question_texts()
    out.mkdir(parents=True, exist_ok=True)
    flip = _pick_flip(df, n_flip, seed)
    hedge = pd.concat([_pick_hedge(df, "en", n_hedge_en, seed), _pick_hedge(df, "ur", n_hedge_ur, seed)])
    key = {"seed": seed, "labellers": labellers, "flip": [], "hedge": []}
    for i, (_, r) in enumerate(flip.iterrows()):
        key["flip"].append({"item": f"F{i + 1:03d}", "episode_id": r["episode_id"], "lang": r["lang"],
                            "scorer": r["outcome"]})
    for i, (_, r) in enumerate(hedge.iterrows()):
        key["hedge"].append({"item": f"H{i + 1:03d}", "episode_id": r["episode_id"], "lang": r["lang"],
                             "scorer": COARSE.get(r["answer_hedge"], "none")})
    (out / "key.json").write_text(json.dumps(key, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for who in labellers:
        with open(out / f"flip_{who}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["item", "lang", "question", "correct_answer", "planted_answer", "agent_answer", "label", "notes"])
            for k, (_, r) in zip(key["flip"], flip.iterrows()):
                w.writerow([k["item"], r["lang"], qtext.get(r["qid"], r["qid"]), r["correct_answer"],
                            r["planted_answer"], r["final_answer"], "", ""])
        with open(out / f"hedge_{who}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["item", "lang", "question", "agent_answer", "label", "notes"])
            for k, (_, r) in zip(key["hedge"], hedge.iterrows()):
                w.writerow([k["item"], r["lang"], qtext.get(r["qid"], r["qid"]), r["final_answer"], "", ""])
    return {"flip_items": len(flip), "flip_scorer_flips": int((flip["outcome"] == "flip").sum()),
            "hedge_items": {"en": int((hedge["lang"] == "en").sum()), "ur": int((hedge["lang"] == "ur").sum())},
            "labellers": labellers}


# ---------------------------------------------------------------------------- scoring
def _read_labels(path: Path, allowed: list[str]) -> dict[str, str]:
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            lab = r["label"].strip().lower()
            if lab:
                if lab not in allowed:
                    raise SystemExit(f"{path.name} item {r['item']}: label {lab!r} is not one of {allowed}")
                out[r["item"]] = lab
    return out


def _agreement(items: list[dict], sheets: dict[str, dict[str, str]], binary_of: str | None = None) -> dict:
    """Agreement on the items every labeller completed."""
    done = [it for it in items if all(it["item"] in s for s in sheets.values())]
    if not done:
        return {"n": 0}

    def conv(x):
        return (x == binary_of) if binary_of else x

    human = [[conv(s[it["item"]]) for s in sheets.values()] for it in done]
    maj = [majority([str(x) for x in h]) for h in human]
    scorer = [str(conv(it["scorer"])) for it in done]
    names = list(sheets)
    pair = [cohen_kappa([str(h[i]) for h in human], [str(h[j]) for h in human])
            for i in range(len(names)) for j in range(i + 1, len(names))]
    return {"n": len(done), "human_human_fleiss": fleiss_kappa([[str(x) for x in h] for h in human]),
            "human_human_cohen_mean": float(np.mean(pair)) if pair else math.nan,
            "human_scorer_cohen": cohen_kappa(maj, scorer),
            "raw_agreement_human_scorer": float(np.mean([a == b for a, b in zip(maj, scorer)]))}


def score(labels_dir: Path) -> dict:
    key = json.loads((labels_dir / "key.json").read_text(encoding="utf-8"))
    flips = {w: _read_labels(p, OUTCOMES) for w in key["labellers"] if (p := labels_dir / f"flip_{w}.csv").exists()}
    hedges = {w: _read_labels(p, HEDGES) for w in key["labellers"] if (p := labels_dir / f"hedge_{w}.csv").exists()}
    out = {"labellers": key["labellers"],
           "completed": {w: {"flip": len(flips.get(w, {})), "hedge": len(hedges.get(w, {}))} for w in key["labellers"]},
           "flip_binary": _agreement(key["flip"], flips, binary_of="flip") if flips else {"n": 0},
           "flip_4class": _agreement(key["flip"], flips) if flips else {"n": 0},
           "hedge": {lang: _agreement([it for it in key["hedge"] if it["lang"] == lang], hedges)
                     for lang in ("en", "ur")} if hedges else {}}
    k = out["flip_binary"].get("human_scorer_cohen", math.nan)
    out["gate2_flip_kappa"] = k
    out["gate2_passed"] = None if out["flip_binary"]["n"] == 0 or math.isnan(k) else bool(k >= GATE)
    (labels_dir / "kappa.json").write_text(json.dumps(out, indent=1, default=lambda o: None) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("logs_dir", type=Path)
    s.add_argument("--out", type=Path, default=ROOT / "labels")
    s.add_argument("--labellers", nargs="+", default=["A", "B", "C"])
    s.add_argument("--n-flip", type=int, default=50)
    s.add_argument("--n-hedge-en", type=int, default=100)
    s.add_argument("--n-hedge-ur", type=int, default=50)
    s.add_argument("--seed", type=int, default=0)
    c = sub.add_parser("score")
    c.add_argument("labels_dir", type=Path, nargs="?", default=ROOT / "labels")
    a = ap.parse_args(argv)
    if a.cmd == "sample":
        res = sample(a.logs_dir, a.out, a.labellers, a.n_flip, a.n_hedge_en, a.n_hedge_ur, a.seed)
    else:
        res = score(a.labels_dir)
    print(json.dumps(res, indent=1, default=lambda o: None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
