# OWNER: A — see PLAN.md §2
"""Cache and logger tests. No network: litellm.completion is monkeypatched."""

import json
import threading
from types import SimpleNamespace as NS

import litellm
import pydantic
import pytest

from contracts.schemas import LogLine
from planted.agent.cache import Cache, cache_key, call_model_cached
from planted.agent.logger import JsonlLogger, without_ts

MSGS = [{"role": "user", "content": "Velmora? ویلمورا"}]


@pytest.fixture
def counting_completion(monkeypatch):
    calls = {"n": 0}

    def fake(**kw):
        calls["n"] += 1
        msg = NS(content=f"answer {calls['n']}", tool_calls=None)
        return NS(
            choices=[NS(message=msg, finish_reason="stop")],
            usage=NS(prompt_tokens=10, completion_tokens=5),
        )

    monkeypatch.setattr(litellm, "completion", fake)
    return calls


def test_cache_hit_identical_and_no_second_call(tmp_path, counting_completion):
    cache = Cache(tmp_path / "llm.sqlite")
    a = call_model_cached("gflite", MSGS, seed=0, cache=cache)
    b = call_model_cached("gflite", MSGS, seed=0, cache=cache)
    assert counting_completion["n"] == 1
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert (cache.hits, cache.misses) == (1, 1)
    assert cache.spent_usd == pytest.approx(a["cost_usd"])
    # Alias and full name share an entry; a fresh Cache object on the same file still hits.
    c = call_model_cached("gemini/gemini-2.5-flash-lite", MSGS, seed=0, cache=Cache(cache.path))
    assert c == a and counting_completion["n"] == 1


def test_cache_key_changes_with_inputs():
    base = dict(model="gflite", seed=0, temperature=0, max_tokens=400, messages=MSGS, tools=None)
    k = cache_key(**base)
    assert cache_key(**(base | {"seed": 1})) != k
    assert cache_key(**(base | {"max_tokens": 401})) != k
    assert cache_key(**(base | {"model": "gemini/gemini-2.5-flash-lite"})) == k


def test_cache_threads(tmp_path, counting_completion):
    cache = Cache(tmp_path / "llm.sqlite")
    out = []

    def work(i):
        out.append(call_model_cached("gflite", [{"role": "user", "content": str(i % 3)}],
                                     cache=cache))

    threads = [threading.Thread(target=work, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(out) == 12
    by_prompt = {}
    for i in range(3):
        by_prompt[i] = cache.get(cache_key("gflite", 0, 0, 400,
                                           [{"role": "user", "content": str(i)}], None))
    assert all(r in by_prompt.values() for r in out)


def logline(**kw):
    base = dict(
        arm="A", k=3, label="wire", tier="T1", lang="en", source_hedge=None, n_agree=None,
        defense="none", model="gemini-2.5-flash-lite", seed=0,
        episode_id="A-k3-wire-T1-en-none-gflite-s0-fx-known-001", qid="fx-known-001",
        regime="known", queries=["q"], opened=[], final_answer="1987", normalised="1987",
        correct_answer="1987", planted_answer="2003", outcome="correct", answer_hedge="none",
        guard_summary=None, tokens_in=10, tokens_out=5, latency_ms=12, cost_usd=0.0,
        ts="2026-11-14T00:00:00Z",
    )
    return base | kw


@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings")
def test_logger_rejects_invalid(tmp_path):
    log = JsonlLogger(tmp_path / "logs" / "run.jsonl")
    with pytest.raises(pydantic.ValidationError):
        log.write(logline(outcome="maybe"))
    with pytest.raises(pydantic.ValidationError):
        log.write(LogLine.model_construct(**logline(tokens_in="many")))
    assert not log.path.exists() or log.path.read_text("utf-8") == ""


def test_logger_writes_canonical_line(tmp_path):
    log = JsonlLogger(tmp_path / "run.jsonl")
    log.write(LogLine(**logline()))
    log.write(logline(ts="2026-11-15T09:00:00Z"))
    raw = log.path.read_bytes()
    assert b"\r\n" not in raw
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 2
    d = json.loads(lines[0])
    assert list(d) == sorted(d)
    assert lines[0] == json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert lines[0] != lines[1]
    assert without_ts(lines[0]) == without_ts(lines[1])
