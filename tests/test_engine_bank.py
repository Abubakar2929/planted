"""MockEngine bank mode against B's real bank (data/pages/main) and question files."""

import json
from pathlib import Path

import pytest

from contracts.schemas import Condition
from planted.engine import MockEngine, PoolError, make_episode_id
from planted.engine.mock_engine import HIDDEN_FIELDS

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "data" / "pages" / "main"
QDIR = ROOT / "data" / "questions"
FILES = ["dev20", "single_origin", "syndication", "urdu60", "hedge150"]

pytestmark = pytest.mark.skipif(not (BANK / "pages.jsonl").exists(), reason="no page bank")


@pytest.fixture(scope="module")
def engine():
    return MockEngine.from_bank(str(BANK), [str(QDIR / f"{f}.jsonl") for f in FILES])


def cond(q, k=3, label="wire", tier="T1", **kw):
    base = dict(arm="A", k=k, label=label, tier=tier, lang=q.lang, source_hedge=None,
                n_agree=None, defense="none", model="gflite31", seed=0)
    return Condition(**(base | kw))


def dev20(engine):
    ids = [json.loads(l)["qid"] for l in open(QDIR / "dev20.jsonl", encoding="utf-8") if l.strip()]
    return [engine.questions[i] for i in ids]


def test_every_dev20_question_builds_ten_pages(engine):
    rejected = []
    for q in dev20(engine):
        for k in (0, 3, 8):
            try:
                pool = engine.build_pool(q, cond(q, k=k))
            except PoolError as e:  # listed, not failed: data/pools.py decides what exists
                rejected.append(f"{q.qid} k={k}: {e}")
                continue
            assert len(pool) == 10
            assert len({p.url for p in pool}) == 10
            assert sum(p.planted for p in pool) == k
            assert all(p.tier == "T1" and p.label == "wire" for p in pool if p.planted)
    print("rejected:", rejected)
    assert len(rejected) < 3 * len(dev20(engine))


def test_two_engines_same_order(engine):
    other = MockEngine.from_bank(str(BANK), [str(QDIR / "dev20.jsonl")])
    for q in dev20(engine)[:5]:
        c = cond(q)
        eid = make_episode_id(c, q.qid)
        engine.start_episode(eid, q, c)
        other.start_episode(eid, other.questions[q.qid], c)
        a = [r.url for r in engine.search(eid, "x", q.lang)]
        assert a == [r.url for r in other.search(eid, "y", q.lang)]
        assert [r.rank for r in engine.search(eid, "x", q.lang)] == list(range(1, 11))


def test_search_and_open_hide_hidden_fields(engine):
    q = dev20(engine)[0]
    c = cond(q, k=8)
    eid = make_episode_id(c, q.qid)
    engine.start_episode(eid, q, c)
    results = engine.search(eid, q.question, q.lang)
    for r in results:
        d = json.loads(r.model_dump_json())
        assert set(d) == {"rank", "url", "title", "snippet"}
        assert not set(d) & set(HIDDEN_FIELDS)
        assert isinstance(engine.open_url(eid, r.url), str)
    assert engine.open_url(eid, "https://nowhere.example/x") == "Page not found"
    trace = engine.episode_trace(eid)
    assert trace["queries"] == [q.question]
    assert trace["opened"] == [r.url for r in results]


def _first(engine, suffix_file):
    qid = json.loads(open(QDIR / f"{suffix_file}.jsonl", encoding="utf-8").readline())["qid"]
    return engine.questions[qid]


@pytest.mark.parametrize("name,regime,lang", [
    ("single_origin", "single_origin", "en"),
    ("syndication", "syndication", "en"),
    ("urdu60", None, "ur"),
])
def test_variant_files_build_planted_pools(engine, name, regime, lang):
    q = _first(engine, name)
    assert q.lang == lang and (regime is None or q.regime == regime)
    c = cond(q, k=3)
    pool = engine.build_pool(q, c)
    assert len(pool) == 10
    planted = [p for p in pool if p.planted]
    assert len(planted) == c.k == 3
    assert all(p.tier == c.tier and p.label == c.label for p in planted)
    assert all(p.lang == c.lang for p in pool)


def test_hedge_file_builds_arm_d_pool(engine):
    q = _first(engine, "hedge150")
    assert q.regime == "hedge"
    c = cond(q, k=0, label=None, tier=None, arm="D", source_hedge="may", n_agree=3)
    pool = engine.build_pool(q, c)
    assert len(pool) == 10
    assert not any(p.planted for p in pool)
    assert sum(p.source_hedge == c.source_hedge for p in pool) == c.n_agree
    assert make_episode_id(c, q.qid).startswith("D-k0-na-na-en-hmay-a3-none-gflite31-s0-")
