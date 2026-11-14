# OWNER: B — see PLAN.md §2
"""Validate B's data against contracts/schemas.py and the data invariants.

    python -m data.generator.validate                 # main bank + questions
    python -m data.generator.validate --bank data/heldout/pages --questions data/questions

Hard checks (any failure exits non-zero):
  - every question / page validates against Contract 1; qids and urls are unique; index <-> pages 1:1
  - all domains are *.example; phone numbers only in the +1-555-0100..0199 fiction range;
    no real outlet names (blocklist below)
  - honest / official / syndicated pages state the true answer and never the planted one
  - filler pages state neither answer
  - planted pages state the planted answer, never the true one; campaign_id = <qid>-<tier>-<label>;
    T0 pages share a verbatim core; T3 campaigns mix both languages
  - hedge pages carry the level the lexicon detects; non-hedge pages carry no hedge marker
  - dev and test never share a fact
Report (printed, not enforced): word-5-gram Jaccard between page pairs, by relation.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from contracts.schemas import Page, Question
from data.lexicons.lexicon import detect_hedge
from data.pools import base_qid

DATA = Path(__file__).resolve().parents[1]
QUESTION_FILES = ["dev20", "test", "single_origin", "syndication", "urdu60", "hedge150"]
REAL_OUTLETS = re.compile(
    r"\b(reuters|associated press|ap news|bbc|cnn|fox news|al jazeera|aljazeera|pravda|sputnik|russia today|"
    r"new york times|washington post|the guardian|bloomberg|dawn news|geo news|ary news|samaa|xinhua|"
    r"perplexity|chatgpt|openai|google|newsguard|emirates)\b", re.IGNORECASE)
PHONE = re.compile(r"\+?\d[\d\-\s()]{8,}\d")
FICTION_PHONE = re.compile(r"^\+1-555-01\d\d$")


def _lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def shingles(text: str, n: int = 5) -> set:
    w = re.findall(r"\w+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def validate(questions_dir: Path, bank_dir: Path, check_questions: bool = True) -> tuple[list[str], dict]:
    errors: list[str] = []
    err = errors.append
    questions: dict[str, Question] = {}
    if check_questions:
        for name in QUESTION_FILES:
            p = questions_dir / f"{name}.jsonl"
            if not p.exists():
                err(f"missing {p}")
                continue
            for d in _lines(p):
                q = Question.model_validate(d)
                if q.qid in questions:
                    err(f"duplicate qid {q.qid}")
                questions[q.qid] = q
        split_of: dict[str, set] = defaultdict(set)
        for q in questions.values():
            split_of[base_qid(q.qid).removesuffix("-ur")].add(q.split)
        for b, s in split_of.items():
            if len(s) > 1:
                err(f"fact {b} appears in both dev and test")

    pages_raw = _lines(bank_dir / "pages.jsonl")
    index = _lines(bank_dir / "index.jsonl")
    if len(pages_raw) != len(index):
        err(f"pages ({len(pages_raw)}) and index ({len(index)}) differ in length")
    pages = [Page.model_validate(d) for d in pages_raw]
    urls = Counter(p.url for p in pages)
    for u, c in urls.items():
        if c > 1:
            err(f"duplicate url {u}")
    by_url = {p.url: p for p in pages}

    # Expected answers per bank qid, in both languages, from the generator's world (the questions only
    # cover the Urdu 60, but T3 campaigns carry Urdu pages for every fact).
    answers = world_answers(bank_dir)
    for q in questions.values():
        if q.regime in ("known", "void", "support", "hedge"):
            exp = answers.get(base_qid(q.qid))
            if exp and (q.correct_answer, q.planted_answer) != exp:
                err(f"question {q.qid}: answers differ from the generator world {exp}")

    campaigns: dict[str, list[Page]] = defaultdict(list)
    for row in index:
        p = by_url.get(row["url"])
        if p is None:
            err(f"index url not in pages: {row['url']}")
            continue
        qid, role = row["qid"], row["role"]
        if not p.domain.endswith(".example") or f"//{p.domain}/" not in p.url:
            err(f"{p.url}: domain must be *.example and match the url")
        text = f"{p.title}\n{p.snippet}\n{p.body}"
        if REAL_OUTLETS.search(text):
            err(f"{p.url}: real outlet/brand name '{REAL_OUTLETS.search(text).group(0)}'")
        for ph in PHONE.findall(text):
            ph = ph.strip()
            if re.search(r"[a-zA-Z]", ph) or len(re.sub(r"\D", "", ph)) < 10:
                continue
            if not FICTION_PHONE.match(ph):
                err(f"{p.url}: phone number outside the fiction range: {ph}")
        if p.lang != row["lang"]:
            err(f"{p.url}: lang mismatch with index")
        if row["lang"] == "ur" and not re.search(r"[؀-ۿ]", p.body):
            err(f"{p.url}: Urdu page has no Urdu script")
        fact_qid = qid.removesuffix("-ur")
        lang_key = fact_qid + ("-ur" if p.lang == "ur" else "")  # answers in the page's own language
        true_a, plant_a = answers.get(lang_key, (None, None))
        if true_a is None:
            err(f"{p.url}: index qid {qid} is not in the generator world")
            continue
        if role in ("honest", "official", "syndicated"):
            if p.planted or p.campaign_id or p.tier:
                err(f"{p.url}: honest page carries planted metadata")
            if p.asserted_answer != true_a or true_a not in p.body:
                err(f"{p.url}: honest page must state the true answer '{true_a}'")
            if plant_a and plant_a in p.body:
                err(f"{p.url}: honest page contains the planted answer")
        elif role == "filler":
            if p.asserted_answer != "none" or p.planted:
                err(f"{p.url}: filler must assert 'none'")
            for a in (true_a, plant_a):
                if a and a != "unknown" and a in p.body:
                    err(f"{p.url}: filler contains an answer '{a}'")
        elif role == "planted":
            if not p.planted or p.tier != row["tier"] or p.label != row["label"]:
                err(f"{p.url}: planted metadata mismatch")
            if p.campaign_id != f"{qid}-{row['tier']}-{row['label']}":
                err(f"{p.url}: campaign_id {p.campaign_id}")
            if plant_a not in p.body or p.asserted_answer != plant_a:
                err(f"{p.url}: planted page must state the planted answer '{plant_a}'")
            if true_a != "unknown" and true_a in p.body:
                err(f"{p.url}: planted page contains the true answer")
            campaigns[p.campaign_id].append(p)
        elif role == "hedge":
            level = row["hedge"]
            if p.source_hedge != level or detect_hedge(p.snippet, p.lang) != level:
                err(f"{p.url}: hedge level {level} not detected (got {detect_hedge(p.snippet, p.lang)})")
            if true_a not in p.body:
                err(f"{p.url}: hedge page must contain the finding '{true_a}'")
        else:
            err(f"{p.url}: unknown role {role}")
        if role in ("honest", "official", "syndicated", "planted") and detect_hedge(p.body, p.lang) != "none":
            err(f"{p.url}: unhedged page contains hedge marker(s) ({detect_hedge(p.body, p.lang)})")

    for cid, ps in campaigns.items():
        if len(ps) < 8:
            err(f"campaign {cid} has {len(ps)} pages (<8)")
        if "-T0-" in cid:
            common = set.intersection(*[set(p.body.split("\n")) for p in ps])
            if not any(ps[0].asserted_answer in line for line in common):
                err(f"T0 campaign {cid} lacks a shared verbatim core")
        if "-T3-" in cid and len({p.lang for p in ps}) < 2:
            err(f"T3 campaign {cid} is not cross-lingual")
        if len({p.domain for p in ps}) != len(ps):
            err(f"campaign {cid} reuses a domain")

    report = similarity_report(index, by_url)
    stats = {"questions": len(questions), "pages": len(pages), "campaigns": len(campaigns),
             "roles": dict(Counter(f"{r['lang']}:{r['role']}" + (f":{r['tier']}" if r["tier"] else "") for r in index)),
             "similarity": report}
    return errors, stats


def world_answers(bank_dir: Path) -> dict[str, tuple[str, str | None]]:
    """{qid or qid-ur: (true answer, planted answer)} rebuilt from the seed in the bank manifest."""
    from data.generator.generate import build_world

    seed = json.loads((bank_dir / "manifest.json").read_text(encoding="utf-8"))["seed"]
    facts, _, _, hedges = build_world(seed)
    out = {}
    for f in facts:
        out[f.fid] = (f.answer_en, f.planted_en)
        out[f.fid + "-ur"] = (f.answer_ur, f.planted_ur)
    for h in hedges:
        out[h.hid] = (h.answer_en, None)
        out[h.hid + "-ur"] = (h.answer_ur, None)
    return out


def similarity_report(index: list[dict], by_url: dict, max_qids: int = 40, seed: int = 0) -> dict:
    """Word-5-gram Jaccard between page pairs by relation, on a sample of questions (EN only)."""
    groups = defaultdict(lambda: defaultdict(list))
    for r in index:
        if r["lang"] != "en":
            continue
        key = r["role"] if r["role"] != "planted" else f"{r['tier']}:{r['label']}"
        groups[r["qid"]][key].append(by_url[r["url"]])
    rng = random.Random(seed)
    qids = sorted(q for q in groups if "honest" in groups[q])
    qids = rng.sample(qids, min(max_qids, len(qids)))
    rel = defaultdict(list)
    for q in qids:
        g = groups[q]
        for key in [k for k in g if k in ("honest", "syndicated", "T0:neutral", "T1:neutral", "T3:neutral", "T4:neutral")]:
            sh = [shingles(p.body) for p in g[key] if p.lang == "en"]
            rel[f"within {key}"] += [jaccard(a, b) for a, b in combinations(sh, 2)]
        if "honest" in g and "T1:neutral" in g:
            hs = [shingles(p.body) for p in g["honest"]]
            ps = [shingles(p.body) for p in g["T1:neutral"]]
            rel["honest vs T1"] += [jaccard(a, b) for a in hs for b in ps]
    out = {}
    for k, v in sorted(rel.items()):
        v = sorted(v)
        out[k] = {"pairs": len(v), "mean": round(sum(v) / len(v), 3), "p95": round(v[int(0.95 * (len(v) - 1))], 3),
                  "share_ge_0.6": round(sum(x >= 0.6 for x in v) / len(v), 3)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", type=Path, default=DATA / "questions")
    ap.add_argument("--bank", type=Path, default=DATA / "pages" / "main")
    a = ap.parse_args(argv)
    errors, stats = validate(a.questions, a.bank)
    print(json.dumps(stats, indent=1, ensure_ascii=False))
    if errors:
        print(f"\n{len(errors)} ERRORS (first 30):")
        for e in errors[:30]:
            print(" -", e)
        return 1
    print("\nOK: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
