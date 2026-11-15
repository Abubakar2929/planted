"""Model roster: every name form resolves, canonical_model maps back to the short alias."""

import pytest

from planted.agent.pricing import PRICES, cost_usd
from planted.engine import make_episode_id
from planted.providers import ROSTER, canonical_model, resolve_model

FORMS = {
    "gflite31": ["gflite31", "gflite", "GFLITE31", "gemini-3.1-flash-lite",
                 "gemini/gemini-3.1-flash-lite", " Gemini/Gemini-3.1-Flash-Lite "],
    "gptoss": ["gptoss", "gpt-oss-120b", "openai/gpt-oss-120b", "groq/openai/gpt-oss-120b"],
    "gptoss20": ["gptoss20", "gpt-oss-20b", "openai/gpt-oss-20b", "groq/openai/gpt-oss-20b"],
}


def test_roster_is_the_three_models():
    assert ROSTER == {
        "gflite31": "gemini/gemini-3.1-flash-lite",
        "gptoss": "groq/openai/gpt-oss-120b",
        "gptoss20": "groq/openai/gpt-oss-20b",
    }


@pytest.mark.parametrize("alias,name", [(a, n) for a, ns in FORMS.items() for n in ns])
def test_every_name_form(alias, name):
    assert resolve_model(name) == ROSTER[alias]
    assert canonical_model(name) == alias


@pytest.mark.parametrize("name", ["gemini-2.5-flash-lite", "gemini/gemini-2.5-flash-lite"])
def test_retired_model_raises(name):
    with pytest.raises(ValueError, match="retired"):
        resolve_model(name)
    with pytest.raises(ValueError, match="retired"):
        canonical_model(name)


def test_unknown_model_passes_through_resolve_but_not_canonical():
    assert resolve_model("gemini/x") == "gemini/x"
    with pytest.raises(ValueError, match="roster"):
        canonical_model("gemini/x")


def test_every_roster_model_has_a_price():
    for full in ROSTER.values():
        assert full in PRICES
        assert cost_usd(full, 1000, 100) > 0


def test_episode_id_uses_canonical_alias():
    from contracts.schemas import Condition

    for name in FORMS["gptoss"]:
        c = Condition(arm="A", k=3, label="wire", tier="T1", lang="en", source_hedge=None,
                      n_agree=None, defense="none", model=name, seed=0)
        assert make_episode_id(c, "q1") == "A-k3-wire-T1-en-none-gptoss-s0-q1"
