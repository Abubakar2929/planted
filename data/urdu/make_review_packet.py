# OWNER: B — see PLAN.md §2
"""Build the Urdu reviewer packet (PLAN.md Phase 2: "send 60 Urdu questions + lexicon to the reviewer").

    python -m data.urdu.make_review_packet

Writes (UTF-8 with BOM, so Excel / Google Sheets open the Urdu correctly):
    data/urdu/review_questions.csv   60 rows: EN question + answer next to the UR question + answer, plus one
                                     honest and one planted UR page sentence for each, and empty reviewer columns
    data/urdu/review_lexicon.csv     every UR hedge marker and qualifier, with its level
The reviewer fills `ok` (y/n), `correction` and `notes`; then run with --apply to record the verdicts in
data/urdu/review_status.json (the paper reports the Urdu set as reviewer-approved only after that).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent


def _rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def build() -> tuple[int, int]:
    en = {q["qid"]: q for q in _rows(DATA / "questions" / "test.jsonl") + _rows(DATA / "questions" / "dev20.jsonl")}
    ur = _rows(DATA / "questions" / "urdu60.jsonl")
    pages = _rows(DATA / "pages" / "main" / "pages.jsonl")
    index = _rows(DATA / "pages" / "main" / "index.jsonl")
    sample: dict[tuple[str, str], str] = {}
    for p, r in zip(pages, index):
        if r["lang"] == "ur" and r["slot"] == 0 and (r["qid"], r["role"]) not in sample:
            if r["role"] in ("honest", "official") or (r["role"] == "planted" and r["tier"] == "T1" and r["label"] == "neutral"):
                sample[(r["qid"], "honest" if r["role"] != "planted" else "planted")] = p["snippet"]
    with open(HERE / "review_questions.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["qid", "regime", "question_en", "answer_en", "question_ur", "answer_ur", "planted_ur",
                    "honest_page_sentence_ur", "planted_page_sentence_ur", "ok", "correction", "notes"])
        for q in ur:
            base = en[q["qid"].removesuffix("-ur")]
            w.writerow([q["qid"], q["regime"], base["question"], base["correct_answer"], q["question"],
                        q["correct_answer"], q["planted_answer"], sample.get((q["qid"], "honest"), ""),
                        sample.get((q["qid"], "planted"), ""), "", "", ""])
    lex = json.loads((DATA / "lexicons" / "hedge_ur.json").read_text(encoding="utf-8"))
    n_lex = 0
    with open(HERE / "review_lexicon.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["level", "kind", "text_ur", "ok", "correction", "notes"])
        for level, spec in lex["levels"].items():
            for m in spec["markers"]:
                w.writerow([level, "marker", m, "", "", ""])
                n_lex += 1
            w.writerow([level, "qualifier", spec["qualifier"], "", "", ""])
            n_lex += 1
        for m in lex["abstain_markers"]:
            w.writerow(["abstain", "marker", m, "", "", ""])
            n_lex += 1
    return len(ur), n_lex


def apply(reviewer: str) -> dict:
    """Record the reviewer's verdicts from the filled CSVs into review_status.json."""
    out = {"reviewer": reviewer, "questions": {}, "lexicon": {}}
    for name, key in (("review_questions.csv", "questions"), ("review_lexicon.csv", "lexicon")):
        with open(HERE / name, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        ok = sum(r["ok"].strip().lower() in ("y", "yes", "1", "ok") for r in rows)
        bad = [r for r in rows if r["ok"].strip().lower() in ("n", "no", "0")]
        blank = sum(not r["ok"].strip() for r in rows)
        out[key] = {"rows": len(rows), "approved": ok, "rejected": len(bad), "unreviewed": blank,
                    "rejections": [{k: r[k] for k in r if k in ("qid", "level", "text_ur", "correction", "notes")} for r in bad]}
    out["approved"] = all(out[k]["unreviewed"] == 0 and out[k]["rejected"] == 0 for k in ("questions", "lexicon"))
    (HERE / "review_status.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", metavar="REVIEWER", help="record verdicts from the filled CSVs")
    a = ap.parse_args(argv)
    if a.apply:
        s = apply(a.apply)
        print(json.dumps({k: s[k] for k in ("approved",)} | {k: {kk: s[k][kk] for kk in ("rows", "approved", "rejected", "unreviewed")} for k in ("questions", "lexicon")}, ensure_ascii=False))
        return 0
    nq, nl = build()
    print(f"wrote review_questions.csv ({nq} questions) and review_lexicon.csv ({nl} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
