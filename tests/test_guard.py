"""Planted Guard on synthetic pages (no bank, no model download: the embedder is always mocked)."""

import copy
import importlib

import pytest

from contracts.schemas import DefenseOut, GuardResult
from planted.baselines import apply_defense
from planted.guard import cluster, config
from planted.guard.cluster import boilerplate_keys, build_graph, domain_stem
from planted.guard.core import DATA_VOID_WARNING, guard, guard_noprov
from planted.guard.hedge import PREFIX, enforce, hedge_floor
from planted.guard.normalize import normalise_text, shingles

guard_pkg = importlib.import_module("planted.guard")
HIDDEN = {"planted", "campaign_id", "label", "tier", "asserted_answer", "source_hedge"}
Q = "In what year was the Velbrook Water Authority founded?"


class FakeEmbedder:
    """Same unit vector for every text (cosine 1.0), counting calls."""

    def __init__(self):
        self.calls = 0

    def __call__(self, texts):
        self.calls += 1
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture(autouse=True)
def fake_embedder(monkeypatch):
    monkeypatch.delenv("PLANTED_GUARD_EMBED", raising=False)
    monkeypatch.delenv("PLANTED_EXTRACT", raising=False)
    fe = FakeEmbedder()
    cluster.set_embedder(fe)
    yield fe
    cluster.set_embedder(None)


def page(i, body, domain=None, author=None, date=None, title=None):
    d = domain or f"outlet{chr(97 + i)}{chr(98 + i)}{chr(99 + i)}.example"
    return {"url": f"https://{d}/velbrook/{i}", "title": title or f"Velbrook story {i}", "snippet": "",
            "content": body, "rank": i + 1, "domain": d, "author": author, "date": date}


COPY = ("The Velbrook Water Authority was founded in 1915, according to a long-forgotten charter that "
        "local historians say settles the question once and for all. Residents remember the old pumping "
        "station and the marsh drainage works that followed in the decades after.")
HONEST = [
    "Since its founding in 1893, the Velbrook Water Authority has managed supply across the valley "
    "and runs three small reservoirs north of the town.",
    "Archive minutes show the Velbrook Water Authority was founded in 1893 by a committee of farmers "
    "worried about the summer droughts on the plain.",
    "Founded in 1893, the Velbrook Water Authority today employs forty people and publishes an annual "
    "report on leakage, metering and river levels.",
]
DOMAINS = ["quorriton.example", "bramblefen.example", "wexhallow.example", "tidmarsh.example",
           "ellacombe.example", "sorvinby.example", "harrowmede.example"]


def copies_plus_honest(n_copies=3, n_honest=2):
    pages = [page(i, COPY, DOMAINS[i], author=f"Writer {i}", date=f"2020-0{i + 1}-01") for i in range(n_copies)]
    pages += [page(n_copies + j, HONEST[j], DOMAINS[n_copies + j], author=f"Reporter {j}",
                   date=f"2021-0{j + 1}-11") for j in range(n_honest)]
    for r, i in zip(pages, range(len(pages))):
        r["rank"] = i + 1
    return pages


# --- normalisation ----------------------------------------------------------------------------

def test_urdu_normalisation_and_char_shingles():
    raw = "يكه ‌ة ۱۸۹۳ عَلی  ٢٣"
    assert normalise_text(raw, "ur") == "یکہ ہ 1893 علی 23"
    assert normalise_text("Ｈｅｌｌｏ‍  World", "en") == "hello world"
    sh = shingles("ویلبروک واٹر", "ur")
    assert all(len(s) == 5 for s in sh) and "ویلبر" in sh
    en = shingles("one two three four five six", "en")
    assert en == {"one two three four five", "two three four five six"}


# --- provenance -------------------------------------------------------------------------------

def test_domain_family_stems():
    assert domain_stem("pelrodale-news.example") == domain_stem("pelrodaledaily.example") == "pelrodale"
    assert domain_stem("pelrodale24.example") == domain_stem("www.thepelrodale-online.example") == "pelrodale"
    assert domain_stem("garholm.example") != domain_stem("pelrodale.example")
    assert domain_stem("news.example") is None


def test_boilerplate_keys_only_distinctive_lines():
    a = {"content": "Pelrodale Courier | Local news\nBy Ysolde Dartara\nText.\nThanks for reading! Leave a comment below."}
    keys = boilerplate_keys(a)
    assert "first:pelrodale courier | local news" in keys and "by:by ysolde dartara" in keys
    assert not any(k.startswith("last:") for k in keys)  # generic genre line is not provenance


def _signals(g, i, j):
    return next(e["signals"] for e in g.edges if (e["i"], e["j"]) == (i, j))


def test_provenance_edges_byline_boilerplate_domain():
    texts = ["Alpha text about rivers and a long story of farming in the valley over many decades.",
             "Beta words concerning bridges, ferries and roads near the coast in winter time.",
             "Gamma notes on festivals, markets and music in the old town square each summer."]
    pages = [
        page(0, "By Hesper Quenwick\n" + texts[0], "quorriton.example"),
        page(1, "By Hesper Quenwick\n" + texts[1], "bramblefen.example"),
        page(2, "Velbrook Evening Mail - local news\n" + texts[2], "pelrodale-news.example"),
        page(3, "Velbrook Evening Mail - local news\n" + texts[0][::-1], "tidmarsh.example"),
        page(4, texts[2][::-1], "pelrodaledaily.example"),
    ]
    g = build_graph(pages, [None] * 5, "en", tau_content=config.TAU_CONTENT, tau_embed=config.TAU_EMBED)
    assert "boilerplate" in _signals(g, 0, 1)            # shared byline
    assert "boilerplate" in _signals(g, 2, 3)            # shared distinctive first line
    assert "domain_family" in _signals(g, 2, 4)          # pelrodale-news / pelrodaledaily
    assert g.cluster_ids[0] == g.cluster_ids[1] and g.cluster_ids[2] == g.cluster_ids[3] == g.cluster_ids[4]
    assert g.cluster_ids[0] != g.cluster_ids[2]


def test_author_date_and_cited_origin_edges():
    pages = [page(0, "Story one about rivers in spring and the floods.", author="Ann Lee", date="2020-01-01"),
             page(1, "Story two about markets and fairs in autumn.", author="Ann Lee", date="2020-01-01"),
             page(2, "Report. Source: Velbrook Gazette archive\nMore words here about weather.", "tidmarsh.example"),
             page(3, "Another. Source: Velbrook Gazette archive\nOther words about trains.", "ellacombe.example")]
    g = build_graph(pages, [None] * 4, "en", tau_content=0.4, tau_embed=0.88)
    assert "author_date" in _signals(g, 0, 1)
    assert "cited_origin" in _signals(g, 2, 3)


# --- the headline behaviour ------------------------------------------------------------------

def test_copies_count_once_honest_answer_wins_by_origins():
    results = copies_plus_honest(3, 2)
    pv = apply_defense("pagevote", Q, results, "en")
    assert pv.system_note.startswith("Most pages (3 of 5) say: 1915")  # page count is fooled
    out = guard(Q, results, "en")
    assert isinstance(out, GuardResult) and isinstance(out, DefenseOut)
    assert out.top_answer_norm == "1893"
    assert out.origins == {"1893": {"pages": 2, "origins": 2}, "1915": {"pages": 3, "origins": 1}}
    assert out.results[0]["extracted_answer"] == "1893" and out.results[1]["extracted_answer"] == "1893"
    copies = [r for r in out.results if r["extracted_answer"] == "1915"]
    assert len({r["cluster_id"] for r in copies}) == 1
    assert out.results[-1]["note"].startswith("Same origin as result #")  # duplicates go last
    assert "'1893' is supported by 2 pages from 2 independent origin(s)" in out.system_note
    assert "'1915' by 3 pages from 1 origin(s)" in out.system_note
    assert all(0.0 <= r["guard_score"] <= 1.0 for r in out.results)
    honest_score = next(r["guard_score"] for r in out.results if r["extracted_answer"] == "1893")
    assert honest_score > max(r["guard_score"] for r in copies)


def test_never_deletes_and_never_mutates():
    results = copies_plus_honest(3, 2) + [page(9, "Unrelated text about cheese and bread.", "harrowmede.example")]
    before = copy.deepcopy(results)
    for fn in (guard, guard_noprov):
        out = fn(Q, results, "en")
        assert sorted(r["url"] for r in out.results) == sorted(r["url"] for r in before)
        assert len(out.results) == len(before)
    assert results == before
    assert guard(Q, [], "en").results == []


def test_gate_fires_with_fewer_than_two_origins():
    out = guard(Q, copies_plus_honest(3, 0), "en")
    assert DATA_VOID_WARNING in out.warnings
    assert out.hedge_floor == "may"
    void = guard(Q, [page(0, "A guide to the valley mentions the authority briefly.")], "en")
    assert DATA_VOID_WARNING in void.warnings and void.top_answer is None


def test_contested_gate_within_margin():
    out = guard(Q, copies_plus_honest(3, 2), "en", overrides={"gate_margin": 1})
    assert any(w.startswith("CONTESTED") for w in out.warnings) and out.hedge_floor == "may"
    out0 = guard(Q, copies_plus_honest(3, 2), "en", overrides={"gate_margin": 0})
    assert not any(w.startswith("CONTESTED") for w in out0.warnings)


def test_origin_tie_broken_by_rank_not_pages_and_contested():
    # one origin of 3 copies vs one independent honest page: equal origins (1 vs 1)
    honest_first = [page(0, HONEST[0], DOMAINS[4])] + \
        [page(i + 1, COPY, DOMAINS[i]) for i in range(3)]
    out = guard(Q, honest_first, "en", overrides={"gate_margin": 0})
    assert out.origins == {"1893": {"pages": 1, "origins": 1}, "1915": {"pages": 3, "origins": 1}}
    assert out.top_answer_norm == "1893"            # best rank wins; 3 pages do not
    assert any(w.startswith("CONTESTED") for w in out.warnings)
    assert out.hedge_floor in ("may", "preliminary", "disagree")
    copies_first = [page(i, COPY, DOMAINS[i]) for i in range(3)] + [page(3, HONEST[0], DOMAINS[4])]
    out2 = guard(Q, copies_first, "en", overrides={"gate_margin": 0})
    assert out2.top_answer_norm == "1915"           # rank decides, and it is always flagged + hedged
    assert any(w.startswith("CONTESTED") for w in out2.warnings) and out2.hedge_floor == "may"


def test_variant_p_paraphrase_edges_off_by_default():
    # fake embedder: cosine 1.0 for every pair, no provenance signals between these pages
    results = [page(i, HONEST[i], DOMAINS[i]) for i in range(3)]
    assert config.TAU_PARA is None
    off = guard(Q, results, "en")
    assert not any("paraphrase" in e["signals"] for e in off.edges)
    on = guard(Q, results, "en", overrides={"tau_para": 0.95})
    assert {(e["i"], e["j"]) for e in on.edges if "paraphrase" in e["signals"]} == {(0, 1), (0, 2), (1, 2)}
    assert on.origins["1893"]["origins"] == 1


def test_hedge_floor_rises_to_preliminary():
    results = [page(0, "Preliminary results suggest the Velbrook Water Authority was founded in 1893.",
                    DOMAINS[0]),
               page(1, HONEST[1], DOMAINS[1]), page(2, HONEST[2], DOMAINS[2])]
    out = guard(Q, results, "en")
    assert out.top_answer_norm == "1893" and out.hedge_floor == "preliminary"
    # P1: the enforced answer is never less hedged than the floor
    from data.lexicons.lexicon import ORDER, detect_hedge
    final = enforce("1893", out.hedge_floor, "en")
    assert ORDER.index(detect_hedge(final, "en")) >= ORDER.index("preliminary")


def test_hedge_floor_helper():
    assert hedge_floor(["none", "none"]) is None
    assert hedge_floor(["none", "may"]) == "may"
    assert hedge_floor(["none"], "may") == "may"
    assert hedge_floor(["preliminary"], "may") == "preliminary"


# --- enforce ----------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["en", "ur"])
@pytest.mark.parametrize("floor", ["may", "preliminary", "disagree"])
def test_enforce_prefixes_and_is_idempotent(lang, floor):
    once = enforce("1893", floor, lang)
    assert once == PREFIX[lang][floor] + "1893"
    assert enforce(once, floor, lang) == once
    assert enforce(enforce(once, "may", lang), floor, lang) == once


def test_enforce_leaves_unfloored_or_already_hedged_answers():
    assert enforce("1893", None, "en") == "1893"
    assert enforce("1893", "none", "en") == "1893"
    assert enforce("It may be 1893.", "may", "en") == "It may be 1893."
    assert enforce("Sources disagree: 1893 or 1915.", "may", "en") == "Sources disagree: 1893 or 1915."
    assert enforce("It may be 1893.", "preliminary", "en").startswith(PREFIX["en"]["preliminary"])
    with pytest.raises(ValueError):
        enforce("x", "certain", "en")


# --- ablation, embeddings, contract --------------------------------------------------------------

def test_guard_noprov_ignores_provenance():
    pages = [page(0, HONEST[0].replace("1893", "1915"), "pelrodale-news.example"),
             page(1, HONEST[1].replace("1893", "1915"), "pelrodaledaily.example"),
             page(2, HONEST[2], "tidmarsh.example")]
    full = guard(Q, pages, "en")
    nop = guard_noprov(Q, pages, "en")
    assert full.origins["1915"]["origins"] == 1          # domain family merges the two
    assert nop.origins["1915"]["origins"] == 2           # content-only graph does not
    assert all(set(e["signals"]) <= {"content"} for e in nop.edges)
    assert any("domain_family" in e["signals"] for e in full.edges)


def test_embedding_edge_needs_weak_provenance(fake_embedder):
    pages = [page(0, HONEST[0], DOMAINS[0], author="Ann Lee", date="2020-01-01"),
             page(1, HONEST[1], DOMAINS[1], author="Ann Lee", date="2021-05-05"),   # same author only
             page(2, HONEST[2], DOMAINS[2], author="Bo Ray", date="2019-03-03")]
    out = guard(Q, pages, "en")
    emb = [e for e in out.edges if "embedding" in e["signals"]]
    assert [(e["i"], e["j"]) for e in emb] == [(0, 1)]   # cosine 1.0 everywhere, but only 0-1 is corroborated
    assert fake_embedder.calls >= 1
    out_off = guard(Q, pages, "en", use_embeddings=False)
    assert not any("embedding" in e["signals"] for e in out_off.edges)


def test_embedding_failure_warns_not_crashes():
    def broken(texts):
        raise OSError("no model")

    cluster.set_embedder(broken)
    pages = [page(0, HONEST[0], DOMAINS[0], author="Ann Lee"), page(1, HONEST[1], DOMAINS[1], author="Ann Lee")]
    out = guard(Q, pages, "en")
    assert any(w.startswith("EMBEDDINGS_UNAVAILABLE") for w in out.warnings)
    assert out.top_answer_norm == "1893"


def test_no_hidden_fields_and_contract_keys():
    results = copies_plus_honest(3, 2)
    for name in ("guard", "guard_noprov"):
        out = apply_defense(name, Q, results, "en")
        assert isinstance(out, DefenseOut)
        for r in out.results:
            assert not HIDDEN & set(r)
            assert {"cluster_id", "guard_score", "note", "extracted_answer", "hedge_level"} <= set(r)
        dumped = out.model_dump()
        assert not HIDDEN & set(dumped)


def test_public_api_and_apply_defense_equivalence():
    import planted

    results = copies_plus_honest(3, 2)
    out = planted.guard(Q, results)
    assert out.origins and out.system_note and out.hedge_floor == "may"
    assert apply_defense("guard", Q, results, "en").model_dump() == out.model_dump()
    assert guard_pkg.guard is guard


def test_urdu_system_note():
    ur = [page(0, "ویلبروک واٹر اتھارٹی ۱۸۹۳ میں قائم ہوئی اور وادی میں پانی فراہم کرتی ہے۔", DOMAINS[0]),
          page(1, "ریکارڈ کے مطابق ویلبروک واٹر اتھارٹی ۱۸۹۳ میں قائم ہوئی تھی اور کسانوں نے بنائی۔", DOMAINS[1])]
    out = guard("ویلبروک واٹر اتھارٹی کس سال قائم ہوئی؟", ur, "ur")
    assert out.top_answer_norm == "1893"
    assert out.system_note.startswith("آزاد ذرائع کی جانچ")


def test_config_frozen_and_hashed():
    import hashlib
    import json

    assert config.FROZEN is True
    assert config.CONFIG_HASH == hashlib.sha256(
        json.dumps(config.values(), sort_keys=True).encode("utf-8")).hexdigest()
    assert guard(Q, copies_plus_honest(), "en").config_hash == config.CONFIG_HASH
