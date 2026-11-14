# OWNER: B — see PLAN.md §2
"""Tests for B's data: contracts, invariants, pools for every planned condition, determinism, lexicons,
the firewall, and the LLM rewriting path (with a fake model, so no keys are needed)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from contracts.schemas import Condition, Page
from data.generator.validate import validate
from data.lexicons.lexicon import detect_hedge, is_abstention, qualify
from data.pools import PageBank, build_pool, load_questions

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
Q = DATA / "questions"
MAIN = DATA / "pages" / "main"
HELDOUT = DATA / "heldout" / "pages"


@pytest.fixture(scope="module")
def main_bank() -> PageBank:
    return PageBank.load(MAIN)


@pytest.fixture(scope="module")
def heldout_bank() -> PageBank:
    return PageBank.load(HELDOUT)


def cond(**kw) -> Condition:
    base = dict(arm="A", k=0, label=None, tier=None, lang="en", source_hedge=None, n_agree=None,
                defense="none", model="test", seed=0)
    base.update(kw)
    return Condition(**base)


# ---------------------------------------------------------------------------- questions
def test_question_files_counts_and_contract():
    expected = {"dev20": 20, "test": 100, "single_origin": 95, "syndication": 95, "urdu60": 60, "hedge150": 150}
    seen = set()
    for name, n in expected.items():
        qs = load_questions(Q / f"{name}.jsonl")
        assert len(qs) == n, name
        for q in qs:
            assert q.qid not in seen
            seen.add(q.qid)
    regimes = Counter(q.regime for q in load_questions(Q / "dev20.jsonl") + load_questions(Q / "test.jsonl"))
    assert regimes == {"known": 80, "void": 25, "support": 15}
    for q in load_questions(Q / "urdu60.jsonl"):
        assert q.lang == "ur" and re.search(r"[؀-ۿ]", q.question)
    support = [q for q in load_questions(Q / "test.jsonl") if q.regime == "support"]
    assert all(re.fullmatch(r"\+1-555-01\d\d", q.correct_answer) for q in support)
    assert all(q.correct_answer == "unknown" for q in load_questions(Q / "test.jsonl") if q.regime == "void")


# ---------------------------------------------------------------------------- banks
@pytest.mark.parametrize("bank_dir", [MAIN, HELDOUT], ids=["main", "heldout"])
def test_bank_passes_all_invariants(bank_dir):
    errors, stats = validate(Q, bank_dir)
    assert errors == [], errors[:10]
    sim = stats["similarity"]
    # The attacker ladder the paper relies on: copies overlap, paraphrases and honest pages do not.
    assert sim["within T0:neutral"]["mean"] > 0.5
    assert sim["within honest"]["share_ge_0.6"] == 0.0
    assert sim["within T1:neutral"]["share_ge_0.6"] == 0.0
    assert sim["within T4:neutral"]["mean"] <= sim["within T1:neutral"]["mean"]


def test_heldout_covers_test_split_only(heldout_bank):
    dev = {q.qid for q in load_questions(Q / "dev20.jsonl")}
    assert not ({r["qid"].removesuffix("-ur") for r in heldout_bank.index} & dev)


# ---------------------------------------------------------------------------- pools
def _check_pool(pool: list[Page], k: int):
    assert len(pool) == 10
    assert len({p.url for p in pool}) == 10
    assert len({p.domain for p in pool}) == 10, "every result comes from a different domain"
    planted = [p for p in pool if p.planted]
    assert len(planted) == k
    assert len({p.campaign_id for p in planted}) <= 1


def test_pools_arm_ab_dose_by_label(main_bank):
    qs = load_questions(Q / "dev20.jsonl") + load_questions(Q / "test.jsonl")
    for q in qs:
        for k in (0, 1, 2, 3, 5, 8):
            for label in ("wire", "propaganda", "blog"):
                pool = build_pool(main_bank, q, cond(arm="B", k=k, label=label, tier="T1" if k else None))
                _check_pool(pool, k)
                assert all(p.label == label for p in pool if p.planted)
                if q.regime == "known":
                    assert sum(p.asserted_answer == q.correct_answer for p in pool) == 10 - k
                if q.regime == "void":
                    assert not any(not p.planted and p.asserted_answer != "none" for p in pool)


def test_pools_guard_conditions_on_heldout(heldout_bank):
    test = load_questions(Q / "test.jsonl")
    so = load_questions(Q / "single_origin.jsonl")
    syn = load_questions(Q / "syndication.jsonl")
    for q in test:
        _check_pool(build_pool(heldout_bank, q, cond(arm="G")), 0)
        for tier, k in (("T0", 3), ("T0", 8), ("T1", 3), ("T1", 5), ("T1", 8), ("T3", 3), ("T3", 8)):
            _check_pool(build_pool(heldout_bank, q, cond(arm="G", k=k, tier=tier)), k)
    for q in [x for x in so if x.split == "test"]:
        pool = build_pool(heldout_bank, q, cond(arm="G"))
        _check_pool(pool, 0)
        assert sum(p.asserted_answer == q.correct_answer for p in pool) == 1
    for q in [x for x in syn if x.split == "test"]:
        pool = build_pool(heldout_bank, q, cond(arm="G"))
        _check_pool(pool, 0)
        assert sum(p.asserted_answer == q.correct_answer for p in pool) == (6 if q.qid.startswith("pl-known") else 4)
    t3 = build_pool(heldout_bank, test[0], cond(arm="G", k=8, tier="T3"))
    assert {p.lang for p in t3 if p.planted} == {"en", "ur"}


def test_pools_hedge_urdu_t4(main_bank, heldout_bank):
    for q in load_questions(Q / "hedge150.jsonl"):
        for level in ("none", "may", "preliminary", "disagree"):
            for n in (1, 3):
                pool = build_pool(main_bank, q, cond(arm="D", source_hedge=level, n_agree=n))
                _check_pool(pool, 0)
                hedged = [p for p in pool if p.source_hedge == level and p.asserted_answer == q.correct_answer]
                assert len(hedged) == n
    for q in load_questions(Q / "urdu60.jsonl"):
        for k in (0, 3, 8):
            for label in ("wire", "propaganda"):
                pool = build_pool(main_bank, q, cond(arm="E", lang="ur", k=k, label=label, tier="T1" if k else None))
                _check_pool(pool, k)
                assert all(p.lang == "ur" for p in pool)
            _check_pool(build_pool(heldout_bank, q, cond(arm="G", lang="ur", k=k, tier="T1" if k else None)), k)
    t4 = json.loads((HELDOUT / "manifest.json").read_text(encoding="utf-8"))["questions_covered"]["t4"]
    assert len(t4) == 20
    byq = {q.qid: q for q in load_questions(Q / "test.jsonl")}
    for qid in t4:
        for k in (3, 8):
            _check_pool(build_pool(heldout_bank, byq[qid], cond(arm="T4", k=k, tier="T4")), k)


def test_pool_order_is_seeded(main_bank):
    q = load_questions(Q / "test.jsonl")[0]
    a = [p.url for p in build_pool(main_bank, q, cond(k=3, tier="T1", seed=0))]
    b = [p.url for p in build_pool(main_bank, q, cond(k=3, tier="T1", seed=0))]
    c = [p.url for p in build_pool(main_bank, q, cond(k=3, tier="T1", seed=1))]
    assert a == b and sorted(a) == sorted(c)


# ---------------------------------------------------------------------------- determinism
def test_regeneration_is_byte_identical(tmp_path, monkeypatch):
    """Regenerating a slice reproduces the committed pages exactly (T4 uses the recorded embedder)."""
    from data.generator.generate import run

    manifest = json.loads((MAIN / "manifest.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("PLANTED_EMBEDDER", "tfidf" if manifest["embedder_t4"] == "char5-tfidf" else "auto")
    from data.generator import embed

    monkeypatch.setattr(embed, "_backend", None)
    only = {"pl-known-001", "pl-void-001", "pl-support-001", "pl-hedge-air-001"}
    run(manifest["seed"], "offline", "none", tmp_path, only=only)
    committed = {}
    for page_line, idx_line in zip(open(MAIN / "pages.jsonl", encoding="utf-8"), open(MAIN / "index.jsonl", encoding="utf-8")):
        if json.loads(idx_line)["qid"].removesuffix("-ur") in only:
            committed[json.loads(page_line)["url"]] = page_line
    regen = {json.loads(l)["url"]: l for l in open(tmp_path / "pages" / "main" / "pages.jsonl", encoding="utf-8")}
    assert regen == committed
    for name in ("dev20", "test", "hedge150", "urdu60"):
        # newline-safe: a Windows checkout may convert the committed LF files to CRLF
        def lf(p):
            return p.read_bytes().replace(b"\r\n", b"\n")

        assert lf(tmp_path / "questions" / f"{name}.jsonl") == lf(Q / f"{name}.jsonl")


# ---------------------------------------------------------------------------- lexicons
def test_lexicon_levels_and_months():
    assert detect_hedge("The authority was founded in 1926.", "en") == "none"
    assert detect_hedge("The line opened on 14 May 1998.", "en") == "none"
    assert detect_hedge("It may have opened in 1998.", "en") == "may"
    assert detect_hedge("A preliminary study suggests a 40% fall.", "en") == "preliminary"
    assert detect_hedge("Others dispute the 40% figure.", "en") == "disagree"
    assert detect_hedge("قصبے کا بازار ہر جمعرات کو لگتا ہے۔", "ur") == "none"
    assert detect_hedge("آبادی شاید 40 فیصد کم ہوئی ہو۔", "ur") == "may"
    assert detect_hedge("ایک ابتدائی تحقیق سے پتا چلتا ہے۔", "ur") == "preliminary"
    assert detect_hedge("ماہرین اس سے اختلاف کرتے ہیں۔", "ur") == "disagree"
    assert detect_hedge(qualify("40%", "preliminary", "en"), "en") == "preliminary"
    assert detect_hedge(qualify("40 فیصد", "disagree", "ur"), "ur") == "disagree"
    assert is_abstention("I could not find reliable information.", "en")


# ---------------------------------------------------------------------------- firewall
def test_data_code_never_touches_guard_or_baselines():
    for py in DATA.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert not re.search(r"(import|from)\s+planted\.(guard|baselines)", src), py


# ---------------------------------------------------------------------------- LLM path (fake model)
def test_llm_backend_rewrites_and_enforces_claim_survival(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the local LLM cache goes to tmp_path/.cache
    from data.generator import generate as G
    from data.generator.llm import LLM

    calls = {"n": 0}

    def fake(messages, seed, model):
        calls["n"] += 1
        prompt = messages[-1]["content"]
        answer = re.search(r'contain the exact string "([^"]+)"', prompt)
        if "Does the text below assert" in prompt:
            return {"content": '{"asserts": true}', "tokens_in": 10, "tokens_out": 3}
        if answer and seed % 2 == 0:  # every other draw "forgets" the claim: must be rejected
            body = f"A fresh local write-up. Records show the figure is {answer.group(1)}. More soon."
        else:
            body = "A write-up that never states the figure."
        return {"content": json.dumps({"title": "LLM title", "body": body}), "tokens_in": 100, "tokens_out": 50}

    facts, _split, _urdu, _ = G.build_world(0)
    fact = next(f for f in facts if f.fid == "pl-known-001")
    gen = G.Generator(0, "offline", "fake")
    gen.backend = "llm"
    gen.llm = LLM("fake-model", complete_fn=fake)
    gen.verifier = LLM("fake-model", temperature=0.0, complete_fn=fake)
    out = G.BankWriter()
    gen.fact_pages(fact, "en", out, fact.fid, G.question(fact, "en", "dev")["question"], ["T1"])
    planted = [p for p, r in zip(out.pages, out.index) if r["role"] == "planted"]
    assert planted and all(fact.planted_en in p["body"] and fact.answer_en not in p["body"] for p in planted)
    assert any("A fresh local write-up" in p["body"] for p in planted)
    n_before = calls["n"]
    gen2 = G.Generator(0, "offline", "fake")
    gen2.backend, gen2.llm, gen2.verifier = "llm", LLM("fake-model", complete_fn=fake), gen.verifier
    gen2.fact_pages(fact, "en", G.BankWriter(), fact.fid, G.question(fact, "en", "dev")["question"], ["T1"])
    assert calls["n"] == n_before, "second run must be served entirely from the cache"


# ---------------------------------------------------------------------------- LLM safeguards
def test_rewrite_checks_reject_unsafe_text():
    from data.generator.checks import rewrite_problem

    ok = "The authority was founded in 1905 to supply the valley."
    assert rewrite_problem(ok, "en", "1905", "1926") is None
    assert rewrite_problem("It was founded in 1926.", "en", "1905", "1926") == "claim missing"
    assert rewrite_problem("Founded in 1905, not 1926 as some say.", "en", "1905", "1926") == "true answer present"
    assert rewrite_problem("It was likely founded in 1905.", "en", "1905", "1926") == "hedged"
    assert rewrite_problem("Reuters says it was founded in 1905.", "en", "1905", "1926") == "real name"
    assert rewrite_problem("Founded in 1905; call +1-212-555-7788.", "en", "1905", "1926") == "non-fiction phone number"


def test_quota_exhaustion_falls_back_to_templates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from data.generator import generate as G
    from data.generator.llm import LLM, QuotaExhausted

    def over_quota(messages, seed, model):
        raise QuotaExhausted("daily quota reached")

    facts, _split, _urdu, _ = G.build_world(0)
    fact = next(f for f in facts if f.fid == "pl-known-001")
    gen = G.Generator(0, "offline", "fake")
    gen.backend = "llm"
    gen.llm = LLM("fake-model", complete_fn=over_quota)
    gen.verifier = gen.llm
    out = G.BankWriter()
    gen.fact_pages(fact, "en", out, fact.fid, G.question(fact, "en", "dev")["question"], ["T1"])
    planted = [r for r in out.index if r["role"] == "planted"]
    assert len(planted) == 32 and all(r["gen"] == "template" for r in planted)
    assert gen.llm.exhausted and gen.reasons.get("quota", 0) >= 1
