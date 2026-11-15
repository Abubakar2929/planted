"""κ tool: textbook values, sampling rules (flips first, hidden scorer labels), scoring end to end."""

from __future__ import annotations

import csv
import json
import math

import pytest

from analysis import kappa as K
from contracts.schemas import LogLine


def test_cohen_and_fleiss_known_values():
    # Cohen: 50 items, po = 0.7, pe = 0.5 -> 0.4 (classic yes/no example)
    a = ["y"] * 25 + ["n"] * 25
    b = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert K.cohen_kappa(a, b) == pytest.approx(0.4)
    assert K.cohen_kappa(a, a) == 1.0
    # Fleiss, Wikipedia worked example (10 items, 14 raters, 5 categories) -> 0.210
    table = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
             [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
    ratings = [[str(c) for c, n in enumerate(row) for _ in range(n)] for row in table]
    assert K.fleiss_kappa(ratings) == pytest.approx(0.210, abs=1e-3)
    assert K.majority(["flip", "correct", "flip"]) == "flip"


def _log(i, **kw) -> str:
    base = dict(arm="A", k=3, label=None, tier="T1", lang="en", source_hedge=None, n_agree=None, defense="none",
                model="sim", seed=0, episode_id=f"e{i}", qid=f"q{i % 40}", regime="known", queries=["q"], opened=[],
                final_answer="1926", normalised="", correct_answer="1926", planted_answer="1905", outcome="correct",
                answer_hedge=None, guard_summary=None, tokens_in=1, tokens_out=1, latency_ms=1, cost_usd=0.0,
                ts="2026-11-15T00:00:00Z")
    base.update(kw)
    return LogLine(**base).model_dump_json()


def test_sample_and_score_end_to_end(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    lines = [_log(i, final_answer="1905" if i % 5 == 0 else "1926") for i in range(200)]
    answers = {"en": ["1926", "It may be 1926.", "Sources disagree; some say 1926."],
               "ur": ["1926", "ممکن ہے کہ 1926 ہو۔", "ذرائع میں اختلاف ہے"]}
    for lang in ("en", "ur"):
        for i in range(150):
            lines.append(_log(1000 + i + (500 if lang == "ur" else 0), arm="D", k=0, lang=lang,
                              source_hedge="may", n_agree=1, planted_answer=None, final_answer=answers[lang][i % 3]))
    (logs / "pilot.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "labels"
    info = K.sample(logs, out, ["A", "B", "C"])
    assert info["flip_items"] == 50 and info["flip_scorer_flips"] >= 25  # flips first: at least half
    assert info["hedge_items"] == {"en": 100, "ur": 50}
    sheet = (out / "flip_A.csv").read_text(encoding="utf-8-sig")
    for hidden in ("scorer", "outcome", "defense", "episode"):
        assert hidden not in sheet.splitlines()[0]
    key = json.loads((out / "key.json").read_text(encoding="utf-8"))

    def fill(name, kind, truth, noise_every=0):
        p = out / f"{kind}_{name}.csv"
        rows = list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))
        for j, r in enumerate(rows):
            lab = truth[r["item"]]
            if noise_every and j % noise_every == 0:
                lab = "drift" if kind == "flip" else ("none" if lab != "none" else "hedged")
            r["label"] = lab
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    flip_truth = {it["item"]: it["scorer"] for it in key["flip"]}
    hedge_truth = {it["item"]: it["scorer"] for it in key["hedge"]}
    for name, noise in (("A", 0), ("B", 0), ("C", 7)):
        fill(name, "flip", flip_truth, noise)
        fill(name, "hedge", hedge_truth, noise)
    res = K.score(out)
    assert res["flip_binary"]["n"] == 50
    assert res["flip_binary"]["human_scorer_cohen"] == 1.0  # majority of A, B (exact) wins over C's noise
    assert 0 < res["flip_binary"]["human_human_fleiss"] < 1
    assert res["gate2_passed"] is True
    assert res["hedge"]["en"]["n"] == 100 and res["hedge"]["ur"]["n"] == 50
    assert (out / "kappa.json").exists()


def test_bad_label_is_rejected(tmp_path):
    p = tmp_path / "flip_A.csv"
    p.write_text("item,label\nF001,flipped\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        K._read_labels(p, K.OUTCOMES)
    assert math.isnan(K.cohen_kappa([], []))
