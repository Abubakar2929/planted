"""Sweep grids, resumable runner, --max-usd stop and prompt styles (no API calls)."""

import json
from collections import Counter
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts.schemas import Condition, DefenseOut, LogLine
from planted.agent.cache import cache_key
from planted.agent.single_call import PROMPT_STYLES, build_messages, episode_id_for
from planted.sweep.grids import build_grid
from planted.sweep.runner import done_ids, run_sweep

ROOT = Path(__file__).resolve().parents[1]
HAVE_DATA = (ROOT / "data" / "questions" / "test.jsonl").exists()


# --------------------------------------------------------------------------- grids
@pytest.mark.skipif(not HAVE_DATA, reason="no question files")
@pytest.mark.parametrize("name,size,n", [
    ("A", "full", 120 * 16 * 3),                    # 5,760
    ("D", "full", 150 * 4 * 2 * 3),                 # 3,600
    ("E", "full", 120 * 5 * 2),                     # 1,200
    ("G", "full", (120 * 8 + 95 * 2) * 5 * 2),      # 11,500 (voids have no -so/-syn variant)
    ("T4", "full", 20 * 2 * 2),                     # 80
    ("UG", "full", 60 * 3 * 2),                     # 360
    ("A", "pilot", 20 * 18 * 2 * 2),                # 1,440
])
def test_grid_sizes(name, size, n):
    runs, _ = build_grid(name, size)
    assert len(runs) == n
    assert len({r.episode_id for r in runs}) == n  # ids unique within a grid


@pytest.mark.skipif(not HAVE_DATA, reason="no question files")
def test_grid_contents():
    a, _ = build_grid("A", "full")
    assert {r.cond.model for r in a} == {"gflite31", "gptoss", "gptoss20"}
    assert {r.cond.k for r in a} == {0, 1, 2, 3, 5, 8} and {r.cond.tier for r in a} == {"T1"}
    assert {r.style for r in a} == {"hedge_ok"}
    g, _ = build_grid("G", "full")
    assert {r.cond.model for r in g} == {"gflite31", "gptoss"}
    assert {r.cond.defense for r in g} == {"none", "prompt", "pagevote", "guard", "guard_noprov"}
    assert {r.question.regime for r in g} >= {"single_origin", "syndication", "known", "void"}
    ug, _ = build_grid("UG", "full")
    assert {r.cond.lang for r in ug} == {"ur"} and {r.cond.arm for r in ug} == {"G"}
    assert all(r.tag == "grid=UG" for r in ug)
    p, _ = build_grid("A", "pilot")
    assert {r.style for r in p} == {"hedge_ok", "neutral"}
    assert all(r.question.split == "dev" for r in p)
    with pytest.raises(SystemExit):
        build_grid("E", "pilot")


# --------------------------------------------------------------------------- prompt styles
def _cond(**kw):
    base = dict(arm="A", k=3, label="wire", tier="T1", lang="en", source_hedge=None, n_agree=None,
                defense="none", model="gflite31", seed=0)
    return Condition(**{**base, **kw})


def test_prompt_style_changes_id_messages_and_cache_key():
    c = _cond()
    assert episode_id_for(c, "q1") == "A-k3-wire-T1-en-none-gflite31-s0-q1"  # Gate 1 id kept
    assert episode_id_for(c, "q1", "neutral").endswith("-q1-neutral")
    with pytest.raises(ValueError):
        episode_id_for(c, "q1", "bogus")
    d = DefenseOut(results=[], system_note=None, warnings=[], hedge_floor=None)
    for st, text in PROMPT_STYLES.items():
        assert build_messages("Q?", [], d, st)[-1]["content"].endswith(text)
    msgs = [{"role": "user", "content": "x"}]
    keys = {cache_key("gflite31", 0, 0, 400, msgs, None, {"prompt_style": s}) for s in PROMPT_STYLES}
    assert len(keys) == 2
    assert cache_key("gflite31", 0, 0, 400, msgs, None) not in keys


# --------------------------------------------------------------------------- runner
def _line(eid: str, outcome="flip") -> LogLine:
    return LogLine(**_cond().model_dump(), episode_id=eid, qid="q", regime="known", queries=[],
                   opened=[], final_answer="a", normalised="a", correct_answer="b",
                   planted_answer="a", outcome=outcome, answer_hedge=None, guard_summary=None,
                   tokens_in=1, tokens_out=1, latency_ms=1, cost_usd=0.5, ts="t")


def _fake(cost=0.5, fail=()):
    cache = SimpleNamespace(spent_usd=0.0, hits=0, misses=0)
    calls, lock = [], threading.Lock()

    def run_fn(run, logger, c):
        with lock:
            calls.append(run.episode_id)
            c.spent_usd += cost
            c.misses += 1
        if run.episode_id in fail:
            raise RuntimeError("boom")
        line = _line(run.episode_id)
        logger.write(line)
        return line
    return cache, calls, run_fn


def _runs(n):
    return [SimpleNamespace(episode_id=f"e{i:03d}", grid="T") for i in range(n)]


def test_resume_skips_done_and_appends(tmp_path):
    out = tmp_path / "log.jsonl"
    cache, calls, fn = _fake(cost=0)
    run_sweep(_runs(5), out, workers=2, cache=cache, run_fn=fn, errors_path=tmp_path / "e.jsonl", progress=False)
    first = out.read_text(encoding="utf-8")
    cache, calls, fn = _fake(cost=0)
    stats = run_sweep(_runs(8), out, workers=3, cache=cache, run_fn=fn, errors_path=tmp_path / "e.jsonl", progress=False)
    assert sorted(calls) == ["e005", "e006", "e007"]
    assert stats["skipped_done"] == 5 and stats["ok"] == 3
    text = out.read_text(encoding="utf-8")
    assert text.startswith(first)  # appended, not overwritten
    assert done_ids(out)[0] == {f"e{i:03d}" for i in range(8)}


def test_errors_logged_and_sweep_continues(tmp_path):
    out, err = tmp_path / "log.jsonl", tmp_path / "errors.jsonl"
    cache, calls, fn = _fake(cost=0, fail={"e002"})
    stats = run_sweep(_runs(5), out, workers=2, cache=cache, run_fn=fn, errors_path=err, progress=False)
    assert stats["ok"] == 4 and stats["errors"] == 1
    (rec,) = [json.loads(l) for l in err.read_text(encoding="utf-8").splitlines()]
    assert rec["episode_id"] == "e002" and "boom" in rec["error"]
    assert "e002" not in done_ids(out)[0]  # retried on the next resume


def test_max_usd_stops_cleanly(tmp_path):
    out = tmp_path / "log.jsonl"
    cache, calls, fn = _fake(cost=0.5)
    stats = run_sweep(_runs(100), out, workers=1, max_usd=2.0, cache=cache, run_fn=fn,
                      errors_path=tmp_path / "e.jsonl", progress=False)
    assert stats["stopped_by_budget"] and len(calls) == 4 and stats["not_started"] == 96
    assert len(done_ids(out)[0]) == 4
    # with several workers the overshoot is bounded by the runs already in flight
    cache, calls, fn = _fake(cost=0.5)
    stats = run_sweep(_runs(100), tmp_path / "log2.jsonl", workers=4, max_usd=2.0, cache=cache,
                      run_fn=fn, errors_path=tmp_path / "e.jsonl", progress=False)
    assert stats["stopped_by_budget"] and 4 <= len(calls) <= 4 + 4


def test_run_py_appends_by_default(tmp_path, monkeypatch):
    import run as run_mod
    import planted.sweep.runner as runner_mod

    out = tmp_path / "log.jsonl"
    out.write_text(_line("old").model_dump_json() + "\n", encoding="utf-8")
    seen = {}

    def fake_sweep(runs, path, **kw):
        seen["text"] = Path(path).read_text(encoding="utf-8")
        return {"outcomes": Counter(), "ok": 0, "errors": 0, "skipped_done": 0, "not_started": 0}

    monkeypatch.setattr(runner_mod, "run_sweep", fake_sweep)
    if not (ROOT / "data" / "pages" / "main" / "pages.jsonl").exists():
        pytest.skip("no page bank")
    monkeypatch.chdir(ROOT)
    run_mod.main(["--arm", "A", "--limit", "1", "--out", str(out)])
    assert "old" in seen["text"]
    run_mod.main(["--arm", "A", "--limit", "1", "--out", str(out), "--overwrite"])
    assert seen["text"] == ""
