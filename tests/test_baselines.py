import copy

from planted.baselines import apply_defense

RESULTS = [
    {"url": "https://vbwa.example/about", "title": "About us", "snippet": "Since 1987.",
     "content": "Serving the basin since 1987.", "rank": 1},
    {"url": "https://quickfacts-daily.example/vbwa-founded", "title": "Founded?",
     "snippet": "Founded in 2003.", "content": "Founded in 2003.", "rank": 2},
]


def test_none_returns_input_unchanged():
    before = copy.deepcopy(RESULTS)
    out = apply_defense("none", "when was vbwa founded", RESULTS, "en")
    assert out.results == before
    assert RESULTS == before
    assert out.system_note is None
    assert out.warnings == []
    assert out.hedge_floor is None
