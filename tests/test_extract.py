"""planted.guard.extract: type inference, typed spans, normalisation, LLM parsing/fallback (no real calls)."""

import pytest

from planted.guard import extract as ex
from planted.guard.extract import extract_answers, infer_answer_type, normalize_answer, parse_llm_reply


def page(content, title="", snippet="", url="https://a.example/x"):
    return {"url": url, "title": title, "snippet": snippet, "content": content, "rank": 1}


# --- type inference -------------------------------------------------------------------------

@pytest.mark.parametrize("q,t", [
    ("In what year was the Yarlodale Basin Water Authority founded?", "year"),
    ("When was the Velton Rowing Club set up?", "year"),
    ("Which year did the mill close?", "year"),
    ("What is the customer support phone number for Torlistead Home Appliances?", "phone"),
    ("What is the helpline for Evvean?", "phone"),
    ("How many bird species have been recorded at the Caldaby Wetland Reserve?", "number"),
    ("What is the population of Velton?", "number"),
    ("How long is the Garholm Bridge, in metres?", "number"),
    ("On what date did the Zelmere Valley Railway open?", "date"),
    ("How much did the new library cost?", "money"),
    ("Who was the first director of the Rildaia Museum of Natural History?", "person"),
    ("In which city is Kordale Instruments Ltd headquartered?", "place"),
    ("What is the mascot of the Brin Rovers called?", "name"),
])
def test_infer_type_en(q, t):
    assert infer_answer_type(q, "en") == t


@pytest.mark.parametrize("q,t", [
    ("یارلوڈیل واٹر اتھارٹی کس سال قائم ہوئی؟", "year"),
    ("ٹورلسٹیڈ ہوم اپلائنسز کا کسٹمر سپورٹ فون نمبر کیا ہے؟", "phone"),
    ("ویلٹن کی آبادی کتنی ہے؟", "number"),
    ("کالڈابی ویٹ لینڈ میں پرندوں کی کتنے اقسام ریکارڈ ہوئی ہیں؟", "number"),
    ("زیلمیر ویلی ریلوے کس تاریخ کو کھلی؟", "date"),
    ("کورڈیل انسٹرومنٹس کا ہیڈ کوارٹر کس شہر میں ہے؟", "place"),
])
def test_infer_type_ur(q, t):
    assert infer_answer_type(q, "ur") == t


# --- normalisation --------------------------------------------------------------------------

def test_normalize_phone_digits_only():
    assert normalize_answer("+1-555-0181", "phone") == "15550181"
    assert normalize_answer("+1 (555) 0181", "phone") == "15550181"


def test_normalize_numbers_and_years():
    assert normalize_answer("23,450", "number") == "23450"
    assert normalize_answer("15.8 thousand", "number") == "15800"
    assert normalize_answer("14%", "number") == "14"
    assert normalize_answer("-65", "number") == "-65"
    assert normalize_answer("in 1893", "year") == "1893"


def test_normalize_dates():
    assert normalize_answer("6 April 1916", "date") == "1916-04-06"
    assert normalize_answer("April 6th, 1916", "date") == "1916-04-06"
    assert normalize_answer("1916-04-06", "date") == "1916-04-06"


def test_normalize_urdu_digits_and_zwnj():
    assert normalize_answer("۱۸۹۳", "year") == "1893"
    assert normalize_answer("٢٣٬٤٥٠", "number") == "23450"
    assert normalize_answer("+۱-۵۵۵-۰۱۸۱", "phone") == "15550181"
    assert normalize_answer("Hesper‌ Quenwick", "person") == "hesper quenwick"


# --- rules extraction -----------------------------------------------------------------------

def test_rules_year_prefers_entity_sentence_over_distractor_year():
    r = page("A guidebook to Fenford published in 2024 gives the Yarlodale Authority a short entry.\n"
             "Since its founding in 1893, the Yarlodale Authority has managed water supply.")
    e = extract_answers("In what year was the Yarlodale Authority founded?", [r], "en")[0]
    assert e["answer"] == "1893" and e["answer_norm"] == "1893"
    assert e["hedge_level"] == "none"
    assert "1893" in e["evidence"] and len(e["evidence"]) <= 200


def test_rules_phone_and_number_with_unit():
    rp = page("Call Torlistead Home Appliances customer support on +1-555-0181, open daily.")
    e = extract_answers("What is the customer support phone number for Torlistead Home Appliances?", [rp], "en")[0]
    assert e["answer_norm"] == "15550181"
    rn = page("On busy days some 33 thousand vehicles cross it. The Garholm Bridge is 521 metres long.")
    e = extract_answers("How long is the Garholm Bridge, in metres?", [rn], "en")[0]
    assert e["answer_norm"] == "521"


def test_rules_person_and_place_strip_function_words():
    r = page("Under Hesper Quenwick, its first director, the Rildaia Museum acquired a mineral hall.")
    e = extract_answers("Who was the first director of the Rildaia Museum?", [r], "en")[0]
    assert e["answer"] == "Hesper Quenwick"
    r = page("For many in Brinkaby, the Garia Weavers' Cooperative is home.\n"
             "The Garia Weavers' Cooperative is based in Brinmoan.")
    e = extract_answers("In which town is the Garia Weavers' Cooperative based?", [r], "en")[0]
    assert e["answer"] == "Brinmoan"


def test_rules_urdu_digits_in_page():
    r = page("یارلوڈیل واٹر اتھارٹی ۱۸۹۳ میں قائم ہوئی۔")
    e = extract_answers("یارلوڈیل واٹر اتھارٹی کس سال قائم ہوئی؟", [r], "ur")[0]
    assert e["answer_norm"] == "1893"


def test_rules_none_when_nothing_matches():
    results = [
        page("Blankets and scarves are woven by hand at the cooperative."),
        page("A community meeting in Darford drew about 16 people last spring."),
        page(""),
    ]
    out = extract_answers("In what year was the Darford Allotment Society founded?", results, "en")
    assert [e["answer"] for e in out] == [None, None, None]
    assert [e["answer_norm"] for e in out] == [None, None, None]
    out = extract_answers("By how much has the eel population in Lake Darford changed since 2017?",
                          results[1:2], "en")
    assert out[0]["answer"] is None


def test_hedge_level_from_lexicon():
    r = page("Preliminary results suggest the eel population in Lake Darford fell by 14%.")
    e = extract_answers("By how much has the eel population in Lake Darford changed since 2017?", [r], "en")[0]
    assert e["answer_norm"] == "14"
    assert e["hedge_level"] == "preliminary"


def test_output_shape_and_order():
    results = [page("The Garholm Bridge is 521 metres long."), page("Nothing here.")]
    out = extract_answers("How long is the Garholm Bridge, in metres?", results, "en")
    assert len(out) == 2
    for e in out:
        assert set(e) == {"answer", "answer_norm", "hedge_level", "evidence"}
        assert e["hedge_level"] in ("none", "may", "preliminary", "disagree")
    assert out[0]["answer_norm"] == "521" and out[1]["answer"] is None


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        extract_answers("q", [], "en", method="magic")


# --- LLM method (call_model_cached mocked; never a real call) ---------------------------------

def test_parse_llm_reply_robust():
    txt = 'Sure:\n```json\n[{"id": 2, "answer": "1915", "hedge": "may"}, {"id": 1, "answer": null}]\n```'
    p = parse_llm_reply(txt, 3)
    assert p[0] == {"answer": None, "hedge": None}
    assert p[1] == {"answer": "1915", "hedge": "may"}
    assert p[2] == {"answer": None, "hedge": None}
    assert parse_llm_reply("not json at all", 2) is None
    assert parse_llm_reply('[{"id": 9, "answer": "x"}]', 2) is None
    assert parse_llm_reply('[{"id": 1, "answer": 1893}]', 1)[0]["answer"] == "1893"


def _mock_llm(monkeypatch, content):
    import planted.agent.cache as cache_mod

    calls = []

    def fake(model, messages, tools=None, seed=0, temperature=0, max_tokens=400, cache=None, key_extra=None):
        calls.append({"model": model, "messages": messages, "seed": seed, "temperature": temperature})
        return {"content": content, "tool_calls": [], "tokens_in": 1, "tokens_out": 1, "latency_ms": 1,
                "cost_usd": 0.0, "raw_finish_reason": "stop"}

    monkeypatch.setattr(cache_mod, "call_model_cached", fake)
    return calls


RESULTS = [page("It is reportedly true that the Yarlodale Authority was founded in 1915.", title="A"),
           page("Since its founding in 1893, the Yarlodale Authority has managed water.", title="B")]
Q = "In what year was the Yarlodale Authority founded?"


def test_llm_method_one_batched_call(monkeypatch):
    calls = _mock_llm(monkeypatch, '[{"id": 1, "answer": "1915", "hedge": "none"}, '
                                   '{"id": 2, "answer": "1893", "hedge": "none"}]')
    out = extract_answers(Q, RESULTS, "en", method="llm", llm_model="gflite31")
    assert len(calls) == 1
    assert calls[0]["seed"] == 0 and calls[0]["temperature"] == 0 and calls[0]["model"] == "gflite31"
    assert "[id=1]" in calls[0]["messages"][-1]["content"] and "[id=2]" in calls[0]["messages"][-1]["content"]
    assert [e["answer_norm"] for e in out] == ["1915", "1893"]
    assert out[0]["hedge_level"] == "may"  # lexicon on the located sentence ("reportedly")


def test_llm_method_falls_back_to_rules_on_bad_json(monkeypatch):
    _mock_llm(monkeypatch, "I cannot answer that.")
    out = extract_answers(Q, RESULTS, "en", method="llm")
    assert out == extract_answers(Q, RESULTS, "en", method="rules")


def test_llm_method_falls_back_on_api_error(monkeypatch):
    import planted.agent.cache as cache_mod

    def boom(*a, **k):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(cache_mod, "call_model_cached", boom)
    out = extract_answers(Q, RESULTS, "en", method="llm")
    assert [e["answer_norm"] for e in out] == ["1915", "1893"]


def test_llm_prompt_truncates_content():
    long = page("x" * 5000)
    msgs = ex.build_llm_messages("q?", [long], "en")
    assert msgs[-1]["content"].count("x") <= ex.LLM_CONTENT_CHARS + 5
