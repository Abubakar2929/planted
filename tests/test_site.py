"""Static scorecard / viewer: builds from logs + results, pending state without results, no secrets."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from contracts.schemas import LogLine
from data.pools import load_questions

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
site_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site_build)


def test_pending_without_results(tmp_path):
    info = site_build.build(tmp_path / "results", tmp_path / "logs", tmp_path / "dist")
    assert info == {"headline": None, "episodes": 0}
    page = (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")
    assert "Results pending" in page and "زیرِ التوا" in page
    assert "No recorded episodes" in (tmp_path / "dist" / "viewer.html").read_text(encoding="utf-8")


@pytest.mark.skipif(not (ROOT / "data" / "pages" / "main" / "pages.jsonl").exists(), reason="page bank not built")
def test_viewer_rebuilds_episode_pools(tmp_path):
    q = {x.qid: x for x in load_questions(ROOT / "data" / "questions" / "test.jsonl")}["pl-support-001"]
    logs = tmp_path / "logs"
    logs.mkdir()
    lines = []
    for k, defense in ((0, "none"), (3, "none"), (3, "guard")):
        lines.append(LogLine(arm="A", k=k, label=None, tier="T1" if k else None, lang="en", source_hedge=None,
                             n_agree=None, defense=defense, model="sim", seed=0, episode_id=f"ep{k}{defense}",
                             qid=q.qid, regime=q.regime, queries=[q.question], opened=[], final_answer=q.correct_answer,
                             normalised="", correct_answer=q.correct_answer, planted_answer=q.planted_answer,
                             outcome="correct", answer_hedge=None, guard_summary=None, tokens_in=1, tokens_out=1,
                             latency_ms=1, cost_usd=0.0, ts="2026-11-14T00:00:00Z").model_dump_json())
    (logs / "run.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (logs / "guard_merges.jsonl").write_text("", encoding="utf-8")
    info = site_build.build(tmp_path / "results", logs, tmp_path / "dist")
    assert info["episodes"] == 3
    eps = site_build.episodes(logs, {"main": ROOT / "data" / "pages" / "main"}, [q.qid])
    assert all(len(e["results"]) == 10 for e in eps)
    assert [sum(r["planted"] for r in e["results"]) for e in eps] == [0, 3, 3]
    viewer = (tmp_path / "dist" / "viewer.html").read_text(encoding="utf-8")
    for hidden in ("campaign_id", "asserted_answer", "API_KEY", "sk-", "gsk_", "AIza"):
        assert hidden not in viewer


def test_headline_from_results(tmp_path):
    res = tmp_path / "results"
    res.mkdir()
    (res / "summary.json").write_text(json.dumps({"runs": 10, "models": ["m"], "hypotheses": {
        "G3": {"estimate": 0.01}, "H2": {"estimate": 1.8}}}), encoding="utf-8")
    (res / "rates.csv").write_text(
        "arm,k,lang,defense,tier,n,flip\nA,3,en,none,T1,10,0.4\nB,3,en,none,T1,30,0.6\n"
        "G,5,en,none,T1,20,0.7\nG,5,en,guard,T1,20,0.2\n", encoding="utf-8")
    (res / "k50.csv").write_text("regime,k50\nknown,4.2\nvoid,1.5\n", encoding="utf-8")
    h = site_build.headline(res)
    assert h["flip3_en"] == pytest.approx(0.55) and h["g5_guard"] == pytest.approx(0.2)
    assert h["k50_min"] == 4.2 and h["label_ratio"] == 1.8 and h["clean_cost"] == 0.01
    page = site_build.scorecard(h)
    assert "55%" in page and "×1.80" in page and "1.0 pts" in page and "Results pending" not in page
