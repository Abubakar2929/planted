# OWNER: A — see PLAN.md §2
"""Provider tests. No network: litellm.completion is monkeypatched."""

import json
from types import SimpleNamespace as NS

import litellm
import pytest

import planted.providers as prov
from planted.agent.pricing import cost_usd
from planted.providers import call_model, normalise_tool_calls, resolve_model


def fake_response(tool_calls=None, content="", pt=100, ct=20, finish="stop"):
    msg = NS(content=content, tool_calls=tool_calls)
    return NS(
        choices=[NS(message=msg, finish_reason=finish)],
        usage=NS(prompt_tokens=pt, completion_tokens=ct),
    )


def test_aliases():
    assert resolve_model("gflite") == "gemini/gemini-2.5-flash-lite"
    assert resolve_model("gflite31") == "gemini/gemini-3.1-flash-lite"
    assert resolve_model("gptoss") == "groq/openai/gpt-oss-120b"
    assert resolve_model("gemini/x") == "gemini/x"


def test_cost():
    assert cost_usd("gemini/gemini-2.5-flash-lite", 1_000_000, 1_000_000) == pytest.approx(0.50)
    assert cost_usd("gemini/gemini-3.1-flash-lite", 2_000, 1_000) == pytest.approx(0.002)
    assert cost_usd("groq/openai/gpt-oss-120b", 1_000_000, 0) == pytest.approx(0.15)
    with pytest.raises(KeyError):
        cost_usd("nope/model", 1, 1)


def test_normalise_openai_object_shape():
    # Groq / OpenAI style: objects with JSON-string arguments.
    calls = [NS(id="c1", function=NS(name="search", arguments='{"query": "hi"}'))]
    assert normalise_tool_calls(calls) == [{"id": "c1", "name": "search", "arguments": {"query": "hi"}}]


def test_normalise_dict_shape():
    # Gemini can return dict arguments; plain dicts are accepted too.
    calls = [
        {"id": None, "function": {"name": "open_url", "arguments": {"url": "https://a.example/"}}},
        {"function": {"name": "search", "arguments": ""}},
        {"function": {"name": "search", "arguments": "{bad json"}},
    ]
    assert normalise_tool_calls(calls) == [
        {"id": None, "name": "open_url", "arguments": {"url": "https://a.example/"}},
        {"id": None, "name": "search", "arguments": {}},
        {"id": None, "name": "search", "arguments": {"_raw": "{bad json"}},
    ]
    assert normalise_tool_calls(None) == []


def test_call_model_result_and_seed(monkeypatch):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return fake_response(
            tool_calls=[NS(id="x", function=NS(name="search", arguments=json.dumps({"query": "q"})))],
            content=None, pt=1000, ct=100, finish="tool_calls",
        )

    monkeypatch.setattr(litellm, "completion", fake)
    r = call_model("gptoss", [{"role": "user", "content": "hi"}], tools=[{"type": "function"}], seed=3)
    assert seen["model"] == "groq/openai/gpt-oss-120b" and seen["seed"] == 3
    assert set(r) == {
        "content", "tool_calls", "tokens_in", "tokens_out", "latency_ms", "cost_usd",
        "raw_finish_reason",
    }
    assert r["content"] == "" and r["tool_calls"][0]["arguments"] == {"query": "q"}
    assert r["cost_usd"] == pytest.approx(cost_usd("groq/openai/gpt-oss-120b", 1000, 100))
    assert r["raw_finish_reason"] == "tool_calls"


def test_retries_rate_limit_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    def fake(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise litellm.RateLimitError("slow down", llm_provider="gemini", model="m")
        return fake_response(content="ok")

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(prov, "_sleep", sleeps.append)
    assert call_model("gflite", [{"role": "user", "content": "hi"}])["content"] == "ok"
    assert calls["n"] == 3 and sleeps == [1.0, 2.0]


def test_gives_up_after_max_tries_and_not_on_bad_request(monkeypatch):
    calls = {"n": 0}

    def fake_5xx(**kw):
        calls["n"] += 1
        raise litellm.InternalServerError("boom", llm_provider="groq", model="m")

    monkeypatch.setattr(prov, "_sleep", lambda s: None)
    monkeypatch.setattr(litellm, "completion", fake_5xx)
    with pytest.raises(litellm.InternalServerError):
        call_model("gptoss", [{"role": "user", "content": "hi"}])
    assert calls["n"] == prov.MAX_TRIES

    calls["n"] = 0

    def fake_400(**kw):
        calls["n"] += 1
        raise litellm.BadRequestError("bad", llm_provider="groq", model="m")

    monkeypatch.setattr(litellm, "completion", fake_400)
    with pytest.raises(litellm.BadRequestError):
        call_model("gptoss", [{"role": "user", "content": "hi"}])
    assert calls["n"] == 1
