# OWNER: B — see PLAN.md §2
"""Generate Contract-1 Questions and Pages (main generator).

    python -m data.generator.generate --seed 0                      # offline backend, everything
    python -m data.generator.generate --seed 0 --backend llm        # LLM tiers (needs .env keys)
    python -m data.generator.generate --seed 0 --only pl-known-001  # one question (debug)

Writes
    data/questions/  dev20.jsonl test.jsonl single_origin.jsonl syndication.jsonl urdu60.jsonl hedge150.jsonl
    data/pages/main/ pages.jsonl (Contract-1 Page per line) + index.jsonl (qid/role/tier/label/slot per url)
                     + manifest.json (counts, backend, embedder, LLM spend)

Design (docs: data/README.md)
    120 facts = 80 known (8 fact types x 10) + 25 void + 15 fake-support-number brands; 20 dev / 100 test,
    stratified by regime. Every page in every tier has a randomised outlet, domain, author, date,
    boilerplate, genre, length and sentence order. All domains are *.example; all phone numbers are in
    the +1-555-0100..0199 fiction range.
    Page roles per question (EN): honest x10 (known), official x1 (support), filler x10, syndicated x3
    (known+support), planted T1 x8 per label {wire, propaganda, blog, neutral}, T0 x8 (neutral, verbatim
    core + shared domain stem), T3 x8 (neutral, alternating EN/UR), T4 x8 (neutral, adaptive).
    Urdu (60 test questions): the same roles in Urdu with T1 labels {wire, propaganda, neutral} and T3
    alternating UR/EN. Hedge claims: 3 independent pages per source-hedge level + 10 fillers.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from data.generator import embed
from data.generator.llm import (
    LLM,
    claim_survives,
    keys_present,
    rewrite_messages,
    translate_messages,
    verify_messages,
)
from data.generator.render import (
    core_paragraph,
    load_bank,
    make_hedge_filler,
    make_hedge_page,
    make_page,
)
from data.generator.world import (
    HEDGE_TYPES,
    QUESTION_TEMPLATES,
    build_fact,
    build_hedge_claim,
    fact_banned,
    make_place,
    safe_name,
)

DATA = Path(__file__).resolve().parents[1]

KNOWN_TYPES = ["founded", "population", "length", "first_director", "headquarters", "opened", "height", "species"]
VOID_TYPES = ["void_founded"] * 9 + ["void_leader"] * 8 + ["void_base"] * 8
N_SUPPORT = 15
DEV_COUNTS = {"known": 13, "void": 4, "support": 3}
URDU_COUNTS = {"known": 40, "void": 12, "support": 8}
HONEST_LABELS = ["neutral", "neutral", "wire", "neutral", "official", "neutral", "blog", "neutral", "wire", "neutral"]
T1_LABELS = {"en": ["wire", "propaganda", "blog", "neutral"], "ur": ["wire", "propaganda", "neutral"]}
N_PLANTED = 8
N_HONEST = 10
N_FILLER = 10
T4_CANDIDATES = 6
HEDGE_LEVELS = ["none", "may", "preliminary", "disagree"]
HEDGE_PER_TYPE = 30
HEDGE_DEV_PER_TYPE = 4


# ---------------------------------------------------------------------------
# World: facts, splits, questions
# ---------------------------------------------------------------------------

def build_world(seed: int):
    used: set[str] = set()
    facts = []
    n = 0
    for ftype in KNOWN_TYPES:
        for _ in range(10):
            n += 1
            facts.append(build_fact(f"pl-known-{n:03d}", ftype, seed, used))
    for i in range(N_SUPPORT):
        facts.append(build_fact(f"pl-support-{i + 1:03d}", "support", seed, used))
    for i, ftype in enumerate(VOID_TYPES):
        facts.append(build_fact(f"pl-void-{i + 1:03d}", ftype, seed, used))
    rng = random.Random(f"split|{seed}")
    split, urdu = {}, set()
    for regime in ("known", "void", "support"):
        ids = [f.fid for f in facts if f.regime == regime]
        rng.shuffle(ids)
        for i, fid in enumerate(ids):
            split[fid] = "dev" if i < DEV_COUNTS[regime] else "test"
        test_ids = [fid for fid in ids if split[fid] == "test"]
        urdu.update(test_ids[: URDU_COUNTS[regime]])
    hedges = []
    for htype in HEDGE_TYPES:
        for i in range(HEDGE_PER_TYPE):
            hedges.append(build_hedge_claim(f"pl-hedge-{htype}-{i + 1:03d}", htype, seed, used))
    return facts, split, urdu, hedges


def question(fact, lang: str, split: str, regime: str | None = None, suffix: str = "") -> dict:
    tmpl = QUESTION_TEMPLATES[fact.ftype][0 if lang == "en" else 1]
    return {
        "qid": fact.fid + suffix + ("-ur" if lang == "ur" else ""), "lang": lang, "split": split,
        "regime": regime or fact.regime, "question": tmpl.replace("{E}", fact.entity_text(lang)),
        "correct_answer": fact.answer(lang), "planted_answer": fact.answer(lang, planted=True),
    }


# ---------------------------------------------------------------------------
# Page banks
# ---------------------------------------------------------------------------

class BankWriter:
    def __init__(self):
        self.pages: list[dict] = []
        self.index: list[dict] = []
        self.urls: set[str] = set()
        self._domains: dict[str, set[str]] = {}

    def taken(self, qid: str) -> set[str]:
        """Domains already used by this question's pages; new random outlets avoid them."""
        return self._domains.setdefault(qid.removesuffix("-ur"), set())

    def add(self, page: dict, qid: str, role: str, tier=None, label=None, slot=None, hedge=None):
        url = page["url"]
        n = 1
        while url in self.urls:  # deterministic de-duplication of colliding slugs
            n += 1
            url = f"{page['url']}-{n}"
        page["url"] = url
        self.urls.add(url)
        self.pages.append(page)
        self.index.append({"qid": qid, "url": url, "role": role, "tier": tier, "label": label,
                           "slot": slot, "lang": page["lang"], "hedge": hedge})


class Generator:
    def __init__(self, seed: int, backend: str, model: str, bank_name: str = "main"):
        self.seed = seed
        self.backend = backend
        self.bank_name = bank_name
        self.banks = {lang: load_bank(bank_name, lang) for lang in ("en", "ur")}
        self.llm = LLM(model) if backend == "llm" else None
        self.verifier = LLM(model, temperature=0.0) if backend == "llm" else None

    def rng(self, *parts) -> random.Random:
        return random.Random("|".join(str(p) for p in (self.seed, self.bank_name) + parts))

    # -- LLM rewriting with claim survival; falls back to the offline page on failure ----------
    def _llm_content(self, fact, lang, answer, forbidden, persona_rng, offline_page, qtext) -> tuple[list[str], str] | None:
        bank = self.banks[lang]
        persona = persona_rng.choice(bank["personas"])
        outlet = offline_page["body"].split("\n")[0]
        ctx = [c for c in offline_page["body"].split("\n")[4:-2] if answer not in c][:4]
        for attempt in range(3):
            seed = persona_rng.randint(0, 2**31 - 1)
            out = self.llm.json(rewrite_messages(qtext, answer, fact.entity_text(lang), persona, outlet,
                                                 lang, ctx), seed=seed)
            if not out or not isinstance(out.get("body"), str):
                continue
            body = out["body"].strip()
            if claim_survives(body, answer, forbidden):
                paras = [p.strip() for p in body.split("\n") if p.strip()]
                return paras, str(out.get("title") or offline_page["title"]).strip()
        self.llm.stats.fallbacks += 1
        return None

    def _planted_page(self, fact, lang, label, tier, slot, cid, qtext, stem=None, family_idx=None,
                      core=None, rng=None, taken=None) -> dict:
        bank = self.banks[lang]
        answer = fact.answer(lang, planted=True)
        forbidden = fact.answer(lang)
        rng = rng or self.rng(fact.fid, lang, tier, label, slot)
        seed_state = rng.getstate()
        page = make_page(fact=fact, bank=bank, lang=lang, rng=rng, label=label, role="planted",
                         planted=True, campaign_id=cid, tier=tier, answer=answer, stem=stem,
                         family_idx=family_idx, core=core, taken=taken)
        if self.backend == "llm" and core is None:
            got = self._llm_content(fact, lang, answer, forbidden, self.rng(fact.fid, lang, tier, label, slot, "llm"),
                                    page, qtext)
            if got:
                paras, title = got
                rng2 = random.Random()
                rng2.setstate(seed_state)  # same outlet as the offline draft (its domain is already reserved)
                page = make_page(fact=fact, bank=bank, lang=lang, rng=rng2, label=label, role="planted",
                                 planted=True, campaign_id=cid, tier=tier, answer=answer, stem=stem,
                                 family_idx=family_idx, content_override=paras, title_override=title)
        return page

    def fact_pages(self, fact, lang: str, out: BankWriter, qid: str, qtext: str, tiers: list[str]) -> None:
        bank = self.banks[lang]
        other = "ur" if lang == "en" else "en"
        if fact.regime == "known":
            for i in range(N_HONEST):
                p = make_page(fact=fact, bank=bank, lang=lang, rng=self.rng(fact.fid, lang, "honest", i),
                              label=HONEST_LABELS[i], role="honest", planted=False, campaign_id=None,
                              tier=None, answer=fact.answer(lang), taken=out.taken(qid))
                out.add(p, qid, "honest", label=HONEST_LABELS[i], slot=i)
        if fact.regime == "support":
            p = make_page(fact=fact, bank=bank, lang=lang, rng=self.rng(fact.fid, lang, "official"),
                          label="official", role="official", planted=False, campaign_id=None, tier=None,
                          answer=fact.answer(lang), taken=out.taken(qid))
            out.add(p, qid, "official", label="official", slot=0)
        for i in range(N_FILLER):
            r = self.rng(fact.fid, lang, "filler", i)
            p = make_page(fact=fact, bank=bank, lang=lang, rng=r, label=r.choice(["neutral", "neutral", "blog"]),
                          role="filler", planted=False, campaign_id=None, tier=None, answer=None,
                          taken=out.taken(qid))
            out.add(p, qid, "filler", label=p["label"], slot=i)
        if fact.regime in ("known", "support"):  # benign syndication: one wire story on 3 domains
            core = core_paragraph(fact, bank, lang, self.rng(fact.fid, lang, "synd-core"), fact.answer(lang))
            for i in range(3):
                p = make_page(fact=fact, bank=bank, lang=lang, rng=self.rng(fact.fid, lang, "synd", i),
                              label="wire", role="syndicated", planted=False, campaign_id=None, tier=None,
                              answer=fact.answer(lang), core=core, title_kind="honest", taken=out.taken(qid))
                out.add(p, qid, "syndicated", label="wire", slot=i)
        if "T1" in tiers:
            for label in T1_LABELS[lang]:
                cid = f"{qid}-T1-{label}"
                for s in range(N_PLANTED):
                    out.add(self._planted_page(fact, lang, label, "T1", s, cid, qtext, taken=out.taken(qid)),
                            qid, "planted", "T1", label, s)
        if "T0" in tiers:
            cid = f"{qid}-T0-neutral"
            r0 = self.rng(fact.fid, lang, "T0-core")
            stem = safe_name(r0, make_place, fact_banned(fact))
            core = core_paragraph(fact, bank, lang, r0, fact.answer(lang, planted=True), planted=True)
            for s in range(N_PLANTED):
                p = self._planted_page(fact, lang, "neutral", "T0", s, cid, qtext, stem=stem, family_idx=s, core=core,
                                       taken=out.taken(qid))
                out.add(p, qid, "planted", "T0", "neutral", s)
        if "T3" in tiers:  # cross-lingual: one campaign, alternating languages (EN<->UR)
            cid = f"{qid}-T3-neutral"
            for s in range(N_PLANTED):
                plang = lang if s % 2 == 0 else other
                p = self._planted_page(fact, plang, "neutral", "T3", s, cid, qtext, taken=out.taken(qid))
                if self.backend == "llm" and plang != lang:
                    p = self._translate(fact, p, plang, lang, s, cid) or p
                out.add(p, qid, "planted", "T3", "neutral", s)
        if "T4" in tiers:
            self._t4(fact, lang, out, qid, qtext)

    def _translate(self, fact, page, plang, src_lang, slot, cid):
        """LLM path for T3: write in the source language, then rewrite into the other language."""
        answer_target = fact.answer(plang, planted=True)
        src = self._planted_page(fact, src_lang, "neutral", "T3-src", slot, cid, "")
        out = self.llm.json(translate_messages(src["title"], src["body"], answer_target, plang),
                            seed=self.rng(fact.fid, "T3-tr", slot).randint(0, 2**31 - 1))
        if not out or not claim_survives(str(out.get("body", "")), answer_target, fact.answer(plang)):
            self.llm.stats.fallbacks += 1
            return None
        paras = [x.strip() for x in str(out["body"]).split("\n") if x.strip()]
        return make_page(fact=fact, bank=self.banks[plang], lang=plang, rng=self.rng(fact.fid, plang, "T3", "neutral", slot),
                         label="neutral", role="planted", planted=True, campaign_id=cid, tier="T3",
                         answer=answer_target, content_override=paras, title_override=str(out.get("title") or src["title"]))

    def _t4(self, fact, lang, out, qid, qtext):
        """Adaptive: per slot, keep the candidate least similar to the campaign pages chosen so far."""
        cid = f"{qid}-T4-neutral"
        chosen_bodies: list[str] = []
        answer = fact.answer(lang, planted=True)
        for s in range(N_PLANTED):
            cands = []
            for c in range(T4_CANDIDATES):
                p = self._planted_page(fact, lang, "neutral", "T4", s, cid, qtext,
                                       rng=self.rng(fact.fid, lang, "T4", s, c), taken=out.taken(qid))
                if not claim_survives(p["body"], answer, fact.answer(lang)):
                    continue
                if self.backend == "llm" and not self._verified(qtext, answer, p["body"], s, c):
                    continue
                cands.append(p)
            if not cands:
                raise RuntimeError(f"T4: no candidate survived for {qid} slot {s}")
            pick = embed.pick_least_similar(chosen_bodies, [c["body"] for c in cands])
            chosen_bodies.append(cands[pick]["body"])
            out.add(cands[pick], qid, "planted", "T4", "neutral", s)

    def _verified(self, qtext, answer, body, s, c) -> bool:
        res = self.verifier.json(verify_messages(qtext, answer, body), seed=1000 * s + c)
        return bool(res and res.get("asserts") is True)

    def hedge_pages(self, claim, out: BankWriter, lang: str = "en") -> None:
        bank = self.banks[lang]
        qid = claim.hid + ("-ur" if lang == "ur" else "")
        for level in HEDGE_LEVELS:
            for i in range(3):
                p = make_hedge_page(claim=claim, bank=bank, lang=lang, rng=self.rng(claim.hid, lang, "hedge", level, i),
                                    level=level, label="neutral" if i != 1 else "wire", taken=out.taken(qid))
                out.add(p, qid, "hedge", label=p["label"], slot=i, hedge=level)
        for i in range(N_FILLER):
            p = make_hedge_filler(claim=claim, bank=bank, lang=lang, rng=self.rng(claim.hid, lang, "hfill", i))
            out.add(p, qid, "filler", label=p["label"], slot=i)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows)


def run(seed: int, backend: str, model: str, out_dir: Path, only: set[str] | None = None,
        tiers: list[str] | None = None) -> dict:
    tiers = tiers or ["T0", "T1", "T3", "T4"]
    if backend == "llm" and not keys_present(model):
        sys.exit(f"--backend llm needs an API key for {model} in .env (see .env.example)")
    facts, split, urdu, hedges = build_world(seed)
    gen = Generator(seed, backend, model)

    qs = {"dev20": [], "test": [], "single_origin": [], "syndication": [], "urdu60": [], "hedge150": []}
    for f in facts:
        sp = split[f.fid]
        qs["dev20" if sp == "dev" else "test"].append(question(f, "en", sp))
        if f.regime in ("known", "support"):
            qs["single_origin"].append(question(f, "en", sp, "single_origin", "-so"))
            qs["syndication"].append(question(f, "en", sp, "syndication", "-syn"))
        if f.fid in urdu:
            qs["urdu60"].append(question(f, "ur", sp))
    for i, h in enumerate(hedges):
        sp = "dev" if int(h.hid.rsplit("-", 1)[1]) <= HEDGE_DEV_PER_TYPE else "test"
        qs["hedge150"].append({"qid": h.hid, "lang": "en", "split": sp, "regime": "hedge", "question": h.q_en,
                               "correct_answer": h.answer_en, "planted_answer": None})

    bank = BankWriter()
    for f in facts:
        if only and f.fid not in only:
            continue
        en_q = question(f, "en", split[f.fid])
        gen.fact_pages(f, "en", bank, f.fid, en_q["question"], tiers)
        if f.fid in urdu:
            ur_q = question(f, "ur", split[f.fid])
            gen.fact_pages(f, "ur", bank, f.fid + "-ur", ur_q["question"], [t for t in tiers if t in ("T1", "T3")])
    for h in hedges:
        if only and h.hid not in only:
            continue
        gen.hedge_pages(h, bank)

    for name, rows in qs.items():  # questions are cheap and always complete, even with --only
        write_jsonl(out_dir / "questions" / f"{name}.jsonl", rows)
    pages_dir = out_dir / "pages" / "main"
    write_jsonl(pages_dir / "pages.jsonl", bank.pages)
    write_jsonl(pages_dir / "index.jsonl", bank.index)
    stats = gen.llm.stats.__dict__ if gen.llm else None
    manifest = {
        "generator": "main", "seed": seed, "backend": backend, "model": model if backend == "llm" else None,
        "embedder_t4": embed.backend_name(), "tiers": tiers,
        "counts": {"questions": {k: len(v) for k, v in qs.items()}, "pages": len(bank.pages)},
        "roles": _role_counts(bank.index), "llm_stats": stats,
    }
    (pages_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _role_counts(index: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in index:
        k = f"{r['lang']}:{r['role']}" + (f":{r['tier']}" if r["tier"] else "")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--backend", choices=["offline", "llm"], default="offline")
    ap.add_argument("--model", default="gemini/gemini-2.5-flash-lite")
    ap.add_argument("--out", type=Path, default=DATA)
    ap.add_argument("--only", nargs="*", help="generate pages for these qids only (debug)")
    ap.add_argument("--tiers", nargs="*", choices=["T0", "T1", "T3", "T4"])
    a = ap.parse_args(argv)
    m = run(a.seed, a.backend, a.model, a.out, set(a.only) if a.only else None, a.tiers)
    print(json.dumps(m["counts"], indent=1))
    if m["llm_stats"]:
        print("llm:", m["llm_stats"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
