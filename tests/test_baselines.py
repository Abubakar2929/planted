import copy

import pytest

from planted.baselines import NO_MAJORITY, PROMPT_NOTE, apply_defense, enforce

RESULTS = [
    {"url": "https://vbwa.example/about", "title": "About us", "snippet": "Since 1987.",
     "content": "Serving the basin since 1987.", "rank": 1},
    {"url": "https://quickfacts-daily.example/vbwa-founded", "title": "Founded?",
     "snippet": "Founded in 2003.", "content": "Founded in 2003.", "rank": 2},
]

HIDDEN = {"planted", "campaign_id", "label", "tier", "asserted_answer", "source_hedge"}
Q = "In what year was the Velbrook Water Authority founded?"


def r(i, text, domain=None):
    d = domain or f"site{i}.example"
    return {"url": f"https://{d}/p{i}", "title": f"Page {i}", "snippet": "", "content": text, "rank": i,
            "domain": d, "author": None, "date": None}


def pool(answers):
    return [r(i, f"The Velbrook Water Authority was founded in {a}.") for i, a in enumerate(answers, start=1)]


def test_none_returns_input_unchanged():
    before = copy.deepcopy(RESULTS)
    out = apply_defense("none", "when was vbwa founded", RESULTS, "en")
    assert out.results == before
    assert RESULTS == before
    assert out.system_note is None
    assert out.warnings == []
    assert out.hedge_floor is None


def test_prompt_adds_note_keeps_order_and_input():
    res = pool(["1893", "1915", "1893"])
    before = copy.deepcopy(res)
    out = apply_defense("prompt", Q, res, "en")
    assert out.system_note == PROMPT_NOTE["en"]
    assert [x["url"] for x in out.results] == [x["url"] for x in before]
    assert res == before  # input not mutated
    assert [x["extracted_answer"] for x in out.results] == ["1893", "1915", "1893"]
    assert all(x["hedge_level"] == "none" for x in out.results)
    assert out.warnings == [] and out.hedge_floor is None


def test_prompt_urdu_note():
    out = apply_defense("prompt", "یہ کب قائم ہوا؟", pool(["1893"]), "ur")
    assert out.system_note == PROMPT_NOTE["ur"] and out.system_note != PROMPT_NOTE["en"]


def test_pagevote_majority_reorders_stably():
    res = pool(["1893", "1915", "1893", "1915", "1915", None])
    res[5]["content"] = "Nothing about it."
    out = apply_defense("pagevote", Q, res, "en")
    urls = [x["url"] for x in out.results]
    assert urls == [res[i]["url"] for i in (1, 3, 4, 0, 2, 5)]
    assert out.system_note == "Most pages (3 of 6) say: 1915."
    assert out.warnings == []
    assert out.hedge_floor is None
    assert out.results[-1]["extracted_answer"] is None


def test_pagevote_tie_warns():
    out = apply_defense("pagevote", Q, pool(["1893", "1915", "1915", "1893"]), "en")
    assert NO_MAJORITY in out.warnings
    assert out.system_note == "Most pages (2 of 4) say: 1893."  # tie -> first in rank order


def test_pagevote_no_answers():
    out = apply_defense("pagevote", Q, [r(1, "Nothing relevant.")], "en")
    assert out.system_note is None and out.warnings == [NO_MAJORITY]


def test_pagevote_urdu_note_uses_urdu_template():
    res = [r(1, "ویلبروک واٹر اتھارٹی ۱۸۹۳ میں قائم ہوئی۔"), r(2, "ویلبروک واٹر اتھارٹی ۱۸۹۳ میں قائم ہوئی۔")]
    out = apply_defense("pagevote", "ویلبروک واٹر اتھارٹی کس سال قائم ہوئی؟", res, "ur")
    assert out.system_note.startswith("زیادہ تر صفحات") and "1893" in out.system_note


@pytest.mark.parametrize("name", ["none", "prompt", "pagevote"])
def test_no_hidden_fields_in_output(name):
    out = apply_defense(name, Q, pool(["1893", "1915", "1893"]), "en")
    for x in out.results:
        assert not HIDDEN & set(x)
    if name != "none":
        assert all({"extracted_answer", "hedge_level"} <= set(x) for x in out.results)


@pytest.mark.parametrize("name", ["guard", "guard_noprov"])
def test_guard_not_implemented_yet(name):
    with pytest.raises(NotImplementedError, match="Guard not implemented yet"):
        apply_defense(name, Q, pool(["1893"]), "en")


def test_unknown_defense():
    with pytest.raises(ValueError):
        apply_defense("delete", Q, [], "en")


def test_enforce_identity_without_floor():
    assert enforce("1893", None, "en") == "1893"
    assert enforce("۱۸۹۳", None, "ur") == "۱۸۹۳"


def test_extract_method_env(monkeypatch):
    from planted.guard import extract as ex  # `import planted.guard.extract` hits the guard() function

    seen = []
    real = ex.extract_answers

    def spy(query, results, lang, method="rules", llm_model="gflite31"):
        seen.append(method)
        return real(query, results, lang, method="rules")

    monkeypatch.setattr(ex, "extract_answers", spy)
    monkeypatch.delenv("PLANTED_EXTRACT", raising=False)
    apply_defense("pagevote", Q, pool(["1893"]), "en")
    monkeypatch.setenv("PLANTED_EXTRACT", "llm")
    apply_defense("pagevote", Q, pool(["1893"]), "en")
    assert seen == ["rules", "llm"]
    monkeypatch.setenv("PLANTED_EXTRACT", "bogus")
    with pytest.raises(ValueError):
        apply_defense("pagevote", Q, pool(["1893"]), "en")
