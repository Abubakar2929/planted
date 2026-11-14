# OWNER: A — see PLAN.md §2
import json
from pathlib import Path

import pytest

from contracts.schemas import Condition
from planted.engine import MockEngine, PoolError, make_episode_id
from planted.engine.mock_engine import NOT_FOUND

FIXTURES = Path(__file__).parent / "fixtures"
HIDDEN = ["planted", "campaign_id", "label", "tier", "asserted_answer", "source_hedge"]


@pytest.fixture(scope="module")
def engine() -> MockEngine:
    return MockEngine(
        [str(FIXTURES / "pages.jsonl"), str(FIXTURES / "pages_engine.jsonl")],
        str(FIXTURES / "questions.jsonl"),
    )


@pytest.fixture(scope="module")
def question(engine):
    return engine.questions["fx-known-001"]


def cond(**kw) -> Condition:
    base = dict(
        arm="A", k=3, label="wire", tier="T1", lang="en", source_hedge=None, n_agree=None,
        defense="none", model="gemini-2.5-flash-lite", seed=0,
    )
    return Condition(**(base | kw))


def test_url_convention_indexes_engine_pages(engine):
    assert len(engine.pages_by_qid["fx-known-001"]) == 24
    # B's shared fixture urls carry no qid, so they are reported, not silently mixed in.
    assert len(engine.unindexed) == 10


@pytest.mark.parametrize("k", [0, 1, 3])
def test_pool_size_and_dose(engine, question, k):
    pool = engine.build_pool(question, cond(k=k))
    assert len(pool) == 10
    assert len({p.url for p in pool}) == 10
    planted = [p for p in pool if p.planted]
    assert len(planted) == k
    assert all(p.label == "wire" and p.tier == "T1" and p.asserted_answer == "2003" for p in planted)


def test_label_none_matches_any_label(engine, question):
    pool = engine.build_pool(question, cond(k=4, label=None))
    assert sum(p.planted for p in pool) == 4


def test_arm_d_agree_and_neutral(engine, question):
    c = cond(arm="D", k=0, label=None, tier=None, source_hedge="may", n_agree=3)
    pool = engine.build_pool(question, c)
    assert len(pool) == 10
    agree = [p for p in pool if p.asserted_answer == "1987"]
    assert len(agree) == 3 and all(p.source_hedge == "may" for p in agree)
    assert all(p.label == "neutral" and not p.planted for p in pool if p not in agree)


def test_search_hides_hidden_fields(engine, question):
    c = cond(k=3)
    eid = make_episode_id(c, question.qid)
    engine.start_episode(eid, question, c)
    results = engine.search(eid, "when was vbwa founded", "en")
    assert [r.rank for r in results] == list(range(1, 11))
    blob = json.dumps([r.model_dump() for r in results])
    for field in HIDDEN:
        assert f'"{field}"' not in blob
    assert all(set(r.model_dump()) == {"rank", "url", "title", "snippet"} for r in results)


def test_same_pool_for_any_query_and_trace(engine, question):
    c = cond(k=1, seed=7)
    eid = make_episode_id(c, question.qid)
    engine.start_episode(eid, question, c)
    a = engine.search(eid, "first query", "en")
    b = engine.search(eid, "something else entirely", "en")
    assert a == b
    url = a[0].url
    engine.open_url(eid, url)
    engine.open_url(eid, "https://nowhere.example/x")
    assert engine.episode_trace(eid) == {
        "queries": ["first query", "something else entirely"],
        "opened": [url],
        "not_found": ["https://nowhere.example/x"],
    }


def test_order_deterministic_and_seed_dependent(engine, question):
    urls = lambda c: [p.url for p in engine.build_pool(question, c)]  # noqa: E731
    assert urls(cond(seed=0)) == urls(cond(seed=0))
    # Fresh engine (new load) gives the same order too.
    fresh = MockEngine(str(FIXTURES / "pages_engine.jsonl"), str(FIXTURES / "questions.jsonl"))
    assert [p.url for p in fresh.build_pool(question, cond(seed=0))] == urls(cond(seed=0))
    assert urls(cond(seed=0)) != urls(cond(seed=1))
    assert sorted(urls(cond(seed=0))) == sorted(urls(cond(seed=1)))


def test_open_url_only_for_pool_urls(engine, question):
    c = cond(k=3)
    eid = make_episode_id(c, question.qid)
    engine.start_episode(eid, question, c)
    pool = engine.episode_pool(eid)
    assert engine.open_url(eid, pool[0].url) == pool[0].body
    in_pool = {p.url for p in pool}
    outside = next(
        p.url for p in engine.pages_by_qid["fx-known-001"] if p.url not in in_pool
    )
    assert engine.open_url(eid, outside) == NOT_FOUND
    with pytest.raises(KeyError):
        engine.open_url("no-such-episode", pool[0].url)


@pytest.mark.parametrize(
    "kw, missing",
    [
        (dict(k=5), "planted pages"),
        (dict(k=1, tier="T3"), "planted pages"),
        (dict(k=0, lang="ur"), "honest pages"),
        (dict(arm="D", k=0, label=None, tier=None, source_hedge="may", n_agree=5), "agree pages"),
        (dict(arm="D", k=0, label=None, tier=None, source_hedge="none", n_agree=1), "neutral"),
    ],
)
def test_pool_error_when_too_few(engine, question, kw, missing):
    with pytest.raises(PoolError, match=missing):
        engine.build_pool(question, cond(**kw))


def test_episode_id_format():
    assert make_episode_id(cond(), "q017") == "A-k3-wire-T1-en-none-gflite-s0-q017"
    d = cond(arm="D", k=0, label=None, tier=None, source_hedge="may", n_agree=3)
    assert make_episode_id(d, "q017") == "D-k0-na-na-en-hmay-a3-none-gflite-s0-q017"
