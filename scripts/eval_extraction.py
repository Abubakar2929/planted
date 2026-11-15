# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Extraction accuracy on dev20 (Gate 2 needs >= 90%). Evaluation only: the ONE place where hidden
Page fields (asserted_answer, source_hedge, planted, tier) are read, to score extraction.
Guard/baseline logic never sees them.

    python scripts/eval_extraction.py                 # rules, dev20, k in {0,3,8}, T0/T1 x wire/propaganda
    python scripts/eval_extraction.py --json out.json
    (also scores the dev rows of hedge150: answer + hedge level vs the hidden source_hedge)

Expected answer per page: the normalised ``asserted_answer``; pages whose asserted_answer is "none"
(fillers that never state the fact) expect None.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contracts.schemas import Condition  # noqa: E402
from planted.engine.mock_engine import MockEngine, PoolError  # noqa: E402
from planted.guard.extract import extract_answers, infer_answer_type, normalize_answer  # noqa: E402

BANK = "data/pages/main"
QUESTIONS = "data/questions/dev20.jsonl"
DOSES = (0, 3, 8)
TIERS = ("T0", "T1")
LABELS = ("wire", "propaganda")
NO_ANSWER = {"none", "", "unknown"}


def conditions(k: int):
    if k == 0:
        yield Condition(arm="A", k=0, label=None, tier=None, lang="en", source_hedge=None, n_agree=None,
                        defense="none", model="gflite31", seed=0)
        return
    for tier in TIERS:
        for label in LABELS + (("neutral",) if tier == "T0" else ()):
            yield Condition(arm="A", k=k, label=label, tier=tier, lang="en", source_hedge=None,
                            n_agree=None, defense="none", model="gflite31", seed=0)


def to_result(p, rank: int) -> dict:
    # Visible keys only, as A's harness builds them (planted.agent.single_call.gather_results).
    return {"url": p.url, "title": p.title, "snippet": p.snippet, "content": p.body, "rank": rank,
            "domain": p.domain, "author": p.author, "date": p.date}


def role_of(p) -> str:
    if p.planted:
        return f"planted-{p.tier}"
    return "filler" if (p.asserted_answer or "").strip().lower() in NO_ANSWER else "true"


def evaluate(method: str = "rules", bank: str = BANK, questions: str = QUESTIONS) -> dict:
    eng = MockEngine.from_bank(str(ROOT / bank), [str(ROOT / questions)])
    rows = []
    skipped = []
    seen_pages: set[tuple[str, str]] = set()
    for q in eng.questions.values():
        if q.split != "dev":
            raise SystemExit(f"refusing to evaluate non-dev question {q.qid}")
        atype = infer_answer_type(q.question, q.lang)
        for k in DOSES:
            for cond in conditions(k):
                cond = cond.model_copy(update={"lang": q.lang})
                try:
                    pages = eng.build_pool(q, cond)
                except PoolError as e:
                    skipped.append(f"{q.qid} k={k} {cond.tier}/{cond.label}: {e}")
                    continue
                results = [to_result(p, i) for i, p in enumerate(pages, start=1)]
                ext = extract_answers(q.question, results, q.lang, method=method)
                for p, e in zip(pages, ext):
                    raw = (p.asserted_answer or "").strip()
                    exp = None if raw.lower() in NO_ANSWER else normalize_answer(raw, atype, q.lang)
                    rows.append({
                        "qid": q.qid, "regime": q.regime, "atype": atype, "k": k, "tier": cond.tier,
                        "label": cond.label, "role": role_of(p), "url": p.url, "title": p.title,
                        "expected_raw": raw, "expected": exp, "extracted_raw": e["answer"],
                        "extracted": e["answer_norm"], "ok": e["answer_norm"] == exp,
                        "evidence": e["evidence"], "unique": (q.qid, p.url) not in seen_pages,
                    })
                    seen_pages.add((q.qid, p.url))
    return {"rows": rows, "skipped": skipped}


HEDGE_QUESTIONS = "data/questions/hedge150.jsonl"
HEDGE_LEVELS = ("none", "may", "preliminary", "disagree")


def evaluate_hedge(bank: str = BANK, questions: str = HEDGE_QUESTIONS) -> dict:
    """Arm-D pools for the dev rows of hedge150: answer and hedge level of the n_agree hedge pages
    (hidden ``source_hedge``), fillers expect no answer."""
    import tempfile

    dev = [line for line in open(ROOT / questions, encoding="utf-8")
           if line.strip() and json.loads(line)["split"] == "dev"]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.writelines(dev)
        dev_path = f.name
    eng = MockEngine.from_bank(str(ROOT / bank), [dev_path])
    Path(dev_path).unlink()
    rows, skipped = [], []
    for q in eng.questions.values():
        atype = infer_answer_type(q.question, q.lang)
        for level in HEDGE_LEVELS:
            for n_agree in (1, 3):
                cond = Condition(arm="D", k=0, label=None, tier=None, lang=q.lang, source_hedge=level,
                                 n_agree=n_agree, defense="none", model="gflite31", seed=0)
                try:
                    pages = eng.build_pool(q, cond)
                except PoolError as e:
                    skipped.append(f"{q.qid} {level}/{n_agree}: {e}")
                    continue
                ext = extract_answers(q.question, [to_result(p, i) for i, p in enumerate(pages, 1)], q.lang)
                for p, e in zip(pages, ext):
                    raw = (p.asserted_answer or "").strip()
                    is_hedge_page = p.source_hedge is not None and raw.lower() not in NO_ANSWER
                    exp = normalize_answer(raw, atype, q.lang) if is_hedge_page else None
                    rows.append({
                        "qid": q.qid, "level": level, "n_agree": n_agree, "hedge_page": is_hedge_page,
                        "expected_raw": raw, "extracted_raw": e["answer"], "ok": e["answer_norm"] == exp,
                        "hedge_expected": p.source_hedge if is_hedge_page else None,
                        "hedge_got": e["hedge_level"], "evidence": e["evidence"], "title": p.title,
                    })
    return {"rows": rows, "skipped": skipped}


def report_hedge(res: dict) -> str:
    rows = res["rows"]
    hp = [r for r in rows if r["hedge_page"]]
    a, c, n = acc(rows)
    lines = [f"Hedge arm (dev rows of hedge150), answer extraction: {a:.1%} ({c} / {n})",
             "", "| source_hedge | answer acc (hedge pages) | hedge level acc | n |", "|---|---|---|---|"]
    for lv in HEDGE_LEVELS:
        g = [r for r in hp if r["hedge_expected"] == lv]
        if g:
            ah = sum(r["ok"] for r in g) / len(g)
            hh = sum(r["hedge_got"] == lv for r in g) / len(g)
            lines.append(f"| {lv} | {ah:.1%} | {hh:.1%} | {len(g)} |")
    misses = [r for r in hp if not r["ok"] or r["hedge_got"] != r["hedge_expected"]]
    seen, shown = set(), 0
    lines.append(f"\nHedge-page misses ({len(misses)}; distinct, first 10):")
    for r in misses:
        key = (r["qid"], r["title"], r["hedge_expected"])
        if key in seen or shown >= 10:
            continue
        seen.add(key)
        shown += 1
        lines.append(f"- [{r['qid']} {r['hedge_expected']}] expected {r['expected_raw']!r} -> {r['extracted_raw']!r}, "
                     f"hedge {r['hedge_got']}: {r['evidence'][:110]!r}")
    if res["skipped"]:
        lines.append(f"\nSkipped pools: {len(res['skipped'])}")
    return "\n".join(lines)


def acc(rows: list[dict]) -> tuple[float, int, int]:
    n = len(rows)
    c = sum(r["ok"] for r in rows)
    return (c / n if n else float("nan")), c, n


def table(rows: list[dict], key: str) -> list[str]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[str(r[key])].append(r)
    out = [f"| {key} | accuracy | correct / n |", "|---|---|---|"]
    for g in sorted(groups):
        a, c, n = acc(groups[g])
        out.append(f"| {g} | {a:.1%} | {c} / {n} |")
    return out


def report(res: dict) -> str:
    rows = res["rows"]
    uniq = [r for r in rows if r["unique"]]
    a, c, n = acc(rows)
    au, cu, nu = acc(uniq)
    lines = [
        f"Overall (all pool slots): {a:.1%} ({c} / {n})",
        f"Overall (unique pages):   {au:.1%} ({cu} / {nu})",
        f"Gate 2 (>= 90%, all slots): {'PASS' if a >= 0.9 else 'FAIL'}",
        "",
        *table(rows, "regime"), "",
        *table(rows, "atype"), "",
        *table(rows, "role"), "",
        *table(rows, "k"), "",
    ]
    misses = [r for r in uniq if not r["ok"]]
    lines.append(f"Worst misses (unique pages; {len(misses)} total, first 10):")
    for r in misses[:10]:
        lines.append(f"- [{r['qid']} {r['role']}] {r['title'][:60]!r}: expected {r['expected_raw']!r} "
                     f"-> extracted {r['extracted_raw']!r}")
    if res["skipped"]:
        lines.append(f"\nSkipped pools ({len(res['skipped'])}):")
        lines.append("  (the main bank has no T0 campaign with that label; T0 is scored on T0/neutral)")
        lines += [f"- {s}" for s in res["skipped"][:3]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--method", default="rules", choices=["rules"],
                    help="only rules here: the llm method makes real calls (rate-limited keys)")
    ap.add_argument("--json", help="write per-page rows to this file")
    ap.add_argument("--misses", type=int, default=0, help="print N extra misses with evidence")
    ap.add_argument("--no-hedge", action="store_true", help="skip the hedge-arm (hedge150 dev rows) section")
    args = ap.parse_args(argv)
    res = evaluate(args.method)
    print(report(res))
    if not args.no_hedge:
        print()
        print(report_hedge(evaluate_hedge()))
    if args.misses:
        print()
        for r in [r for r in res["rows"] if r["unique"] and not r["ok"]][: args.misses]:
            print(json.dumps({k: r[k] for k in ("qid", "role", "expected_raw", "extracted_raw", "evidence")},
                             ensure_ascii=False))
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
