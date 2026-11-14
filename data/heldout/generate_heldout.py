# OWNER: B — see PLAN.md §2
"""HELD-OUT test-page generator for the Guard sweep (PLAN.md §5 Phase 3, firewall rule (c)).

    python -m data.heldout.generate_heldout --seed 0                  # offline backend
    python -m data.heldout.generate_heldout --seed 0 --backend llm    # GPT-OSS-120B on Groq (needs GROQ_API_KEY)

What makes it held out (and why that matters for the paper):
  - a NEW template bank (data/heldout/templates_*.json), written separately from data/templates/, from
    the threat model only ("an operator with N domains wants claim X believed"), never from a defence;
  - a NEW page architecture: forum threads, press releases, FAQ pages, listicles and news briefs, with
    different chrome, outlet naming, domain patterns and a different T0 domain-family scheme;
  - a DIFFERENT LLM family for the rewriting tiers (OpenAI GPT-OSS on Groq vs Gemini in the main bank).
It covers the TEST split only (dev questions are what Guard is tuned on), for the same questions as the
main bank: honest, official, filler and syndicated pages, and planted T0 / T1 / T3 (label neutral) for
all 100 test questions, T4 for 20 test questions, and Urdu pages for the Urdu-60 set.
Output: data/heldout/pages/{pages.jsonl, index.jsonl, manifest.json}, same format as the main bank.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from functools import cache
from pathlib import Path

from data.generator import embed
from data.generator.generate import BankWriter, _gen_counts, _role_counts, build_world, question, write_jsonl
from data.generator.checks import rewrite_problem
from data.generator.llm import (
    LLM,
    QuotaExhausted,
    claim_survives,
    keys_present,
    rewrite_messages,
    translate_messages,
    verify_messages,
)
from data.generator.world import FACT_TYPES, Name, fact_banned, make_person, make_place, safe_name

HERE = Path(__file__).resolve().parent
N_HONEST, N_FILLER, N_PLANTED, T4_CANDIDATES, N_T4_QUESTIONS = 10, 10, 8, 6, 20
HONEST_LABELS = ["neutral", "wire", "neutral", "blog", "neutral", "official", "neutral", "wire", "neutral", "neutral"]
FAMILY = ["{s}-headlines", "{s}247", "the{s}view", "{s}-updates", "{s}world", "my{s}news", "{s}-digest", "{s}hub"]
FAMILY_NAME = ["{S} Headlines", "{S} 24/7", "The {S} View", "{S} Updates", "{S} World", "My {S} News",
               "{S} Digest", "{S} Hub"]


@cache
def bank(lang: str) -> dict:
    return json.loads((HERE / f"templates_{lang}.json").read_text(encoding="utf-8"))


def _f(t: str, m: dict) -> str:
    for k in sorted(m, key=len, reverse=True):
        t = t.replace("{" + k + "}", m[k])
    return t


def fmap(fact, lang: str, answer: str | None) -> dict:
    g = (lambda n: n.en) if lang == "en" else (lambda n: n.ur)
    m = {"E": fact.entity_text(lang), "R": g(fact.region), "N": g(fact.neighbour), "P": g(fact.person),
         "P2": g(fact.person2), "V": g(fact.river), "Y": str(fact.year_ctx), "C": str(fact.num_ctx)}
    if answer is not None:
        m["A"] = answer
    return m


class Source:
    def __init__(self, b: dict, label: str, rng: random.Random, lang: str, m: dict, fact,
                 family: tuple[Name, int] | None = None, taken: set[str] | None = None):
        spec = b["labels"][label]
        banned = fact_banned(fact)
        if label == "official":
            stem = Name(fact.entity.en.split()[0], fact.entity.ur.split()[0])
            self.name = m["E"]
            self.domain = spec["domain"][0].replace("{s}", re.sub(r"[^a-z]", "", stem.en.lower()))
        elif family:
            stem, i = family
            s = re.sub(r"[^a-z]", "", stem.en.lower())
            self.name = FAMILY_NAME[i % len(FAMILY_NAME)].replace("{S}", stem.en if lang == "en" else stem.ur)
            self.domain = FAMILY[i % len(FAMILY)].replace("{s}", s) + ".example"
        else:
            for _ in range(200):  # redraw until the domain is new for this question
                stem = safe_name(rng, make_place, banned)
                s = re.sub(r"[^a-z]", "", stem.en.lower())
                i = rng.randrange(len(spec["outlet"]))
                self.name = spec["outlet"][i].replace("{S}", stem.en if lang == "en" else stem.ur)
                self.domain = spec["domain"][i % len(spec["domain"])].replace("{s}", s)
                if taken is None or self.domain not in taken:
                    break
        if taken is not None:
            taken.add(self.domain)
        person = safe_name(rng, make_person, banned)
        self.au = f"{person.en.split()[1].lower()}{rng.randint(10, 999)}"
        self.author = None if label == "official" or rng.random() < 0.15 else (
            self.au if label == "blog" or rng.random() < 0.3 else (person.en if lang == "en" else person.ur))
        self.date = None if rng.random() < 0.1 else f"{rng.randint(2015, 2026)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        sub = {"O": self.name, "R": m.get("R", ""), "E": m.get("E", "")}
        self.chrome = _f(rng.choice(spec["chrome"]), sub)
        self.extra = spec.get("extra", [])
        self.label = label


def article(b: dict, genre: str, rng: random.Random, m: dict, content: list[str], src_name: str) -> tuple[str, list[str]]:
    """Genre-specific layout of the article text (not the site chrome). Returns (title, lines)."""
    mm = dict(m, O=src_name)
    if genre == "forum":
        g = b["forum"]
        return _f(rng.choice(g["thread"]), mm), [_f(rng.choice(g["op"]), mm), _f(rng.choice(g["reply"]), mm).replace("{au}", rng.choice(["wren", "oriel", "tamsin", "bram", "maren", "silas", "thea", "jory"]) + str(rng.randint(10, 99))),
                                                   *content, _f(rng.choice(g["sign"]), mm)]
    if genre == "press_release":
        g = b["press_release"]
        return _f(rng.choice(g["head"]), mm), [_f(rng.choice(g["dateline"]), mm) + " " + content[0], *content[1:],
                                                 _f(rng.choice(g["end"]), mm)]
    if genre == "qa_page":
        g = b["qa_page"]
        return _f(rng.choice(g["head"]), mm), [_f(rng.choice(g["q"]), mm), ("A: " if b is bank("en") else "جواب: ") + " ".join(content)]
    if genre == "listicle":
        return _f(rng.choice(b["listicle"]["head"]), mm), [f"{i + 1}. {c}" for i, c in enumerate(content)]
    g = b["brief"]
    return _f(rng.choice(g["head"]), mm), [_f(rng.choice(g["dateline"]), mm) + " " + " ".join(content)]


def _ctx(b: dict, fact, rng: random.Random, n: int, m: dict) -> list[str]:
    groups = b["context"]["generic"] + b["context"].get(FACT_TYPES[fact.ftype], [])
    return [_f(rng.choice(g), m) for g in rng.sample(groups, min(n, len(groups)))]


def render(fact, lang: str, rng: random.Random, *, label: str, answer: str | None, planted: bool,
           tier: str | None, cid: str | None, family=None, verbatim: tuple[str, list[str]] | None = None,
           llm_content: tuple[str, list[str]] | None = None, taken: set[str] | None = None) -> dict:
    b = bank(lang)
    m = fmap(fact, lang, answer)
    src = Source(b, label, rng, lang, m, fact, family, taken)
    if verbatim is not None:
        title, lines = verbatim
    elif llm_content is not None:
        title, lines = llm_content
    else:
        if answer is None:
            content = _ctx(b, fact, rng, rng.randint(3, 6), m)
        else:
            claim = _f(rng.choice(b["claims"][fact.ftype]), m)
            content = _ctx(b, fact, rng, rng.randint(1, 4), m)
            content.insert(rng.randint(0, len(content)), claim)
        if src.extra and rng.random() < 0.7:
            content.insert(0, rng.choice(src.extra))
        title, lines = article(b, rng.choice(b["genres"]), rng, m, content, src.name)
    body = [src.chrome] + ([rng.choice(b["chrome_extra"])] if rng.random() < 0.5 else []) + [title] + lines
    body += [rng.choice(b["chrome_extra"]) for _ in range(rng.randint(0, 2))]
    text = "\n".join(body)
    sents = [s for ln in lines for s in re.split(r"(?<=[.!?۔])\s+", ln) if s.strip()]
    snippet = next((s for s in sents if answer and answer in s), sents[0] if sents else title)[:220]
    slug = "-".join(re.findall(r"[a-z0-9]+", fact.entity.en.lower())[:4]) + f"-{rng.randint(10, 99999)}"
    return {"url": f"https://{src.domain}/{rng.choice(b['sections'])}/{slug}", "domain": src.domain, "title": title,
            "snippet": snippet, "body": text, "lang": lang, "author": src.author, "date": src.date,
            "planted": planted, "campaign_id": cid, "label": label, "tier": tier,
            "asserted_answer": answer if answer is not None else "none",
            "source_hedge": None if answer is None else "none"}


class HeldoutGenerator:
    def __init__(self, seed: int, backend: str, model: str, llm_tiers=("T1", "T3", "T4"), llm_langs=("en", "ur"),
                 max_calls: int | None = None):
        self.seed, self.backend = seed, backend
        self.llm = LLM(model, max_calls=max_calls) if backend == "llm" else None
        self.verifier = LLM(model, temperature=0.0, max_calls=max_calls) if backend == "llm" else None
        self.llm_tiers, self.llm_langs = set(llm_tiers), set(llm_langs)
        self.reasons: dict[str, int] = {}

    def _use_llm(self, tier: str, lang: str) -> bool:
        return self.backend == "llm" and tier in self.llm_tiers and lang in self.llm_langs and not self.llm.exhausted

    def _fail(self, reason: str) -> None:
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def rng(self, *p) -> random.Random:
        return random.Random("|".join(map(str, (self.seed, "heldout") + p)))

    def planted(self, fact, lang, tier, s, cid, qtext, family=None, verbatim=None, rng=None, taken=None,
                variant: int = 0) -> dict:
        ans = fact.answer(lang, planted=True)
        rng = rng or self.rng(fact.fid, lang, tier, s)
        if verbatim is None and self._use_llm(tier, lang):
            got = self._llm(fact, lang, ans, fact.answer(lang), qtext, self.rng(fact.fid, lang, tier, s, variant, "llm"))
            if got:
                page = render(fact, lang, rng, label="neutral", answer=ans, planted=True, tier=tier, cid=cid,
                              family=family, llm_content=got, taken=taken)
                page["_gen"] = "llm"
                return page
        return render(fact, lang, rng, label="neutral", answer=ans, planted=True, tier=tier, cid=cid,
                      family=family, verbatim=verbatim, taken=taken)

    def _llm(self, fact, lang, ans, forbidden, qtext, r):
        b = bank(lang)
        persona = r.choice(b["personas"])
        outlet = make_place(r).en + " " + r.choice(["Bulletin", "Newsline", "Forum", "Digest"])
        ctx = _ctx(b, fact, r, 3, fmap(fact, lang, None))
        try:
            for _ in range(3):
                out = self.llm.json(rewrite_messages(qtext, ans, fact.entity_text(lang), persona, outlet, lang, ctx),
                                    seed=r.randint(0, 2**31 - 1))
                if not out or not isinstance(out.get("body"), str):
                    self._fail("bad json")
                    continue
                problem = rewrite_problem(out["body"] + "\n" + str(out.get("title", "")), lang, ans, forbidden)
                if problem is None:
                    return str(out.get("title") or qtext), [p.strip() for p in out["body"].split("\n") if p.strip()]
                self._fail(problem)
        except QuotaExhausted:
            self._fail("quota")
            return None
        self.llm.stats.fallbacks += 1
        return None

    def fact_pages(self, fact, lang: str, out: BankWriter, qid: str, qtext: str, t4: bool) -> None:
        other = "ur" if lang == "en" else "en"
        true = fact.answer(lang)
        if fact.regime == "known":
            for i in range(N_HONEST):
                out.add(render(fact, lang, self.rng(fact.fid, lang, "honest", i), label=HONEST_LABELS[i], answer=true,
                               planted=False, tier=None, cid=None, taken=out.taken(qid)), qid, "honest",
                        label=HONEST_LABELS[i], slot=i)
        if fact.regime == "support":
            out.add(render(fact, lang, self.rng(fact.fid, lang, "official"), label="official", answer=true,
                           planted=False, tier=None, cid=None), qid, "official", label="official", slot=0)
        for i in range(N_FILLER):
            r = self.rng(fact.fid, lang, "filler", i)
            p = render(fact, lang, r, label=r.choice(["neutral", "blog", "neutral"]), answer=None, planted=False,
                       tier=None, cid=None, taken=out.taken(qid))
            out.add(p, qid, "filler", label=p["label"], slot=i)
        if fact.regime in ("known", "support"):
            r = self.rng(fact.fid, lang, "synd-core")
            m = fmap(fact, lang, true)
            b = bank(lang)
            content = _ctx(b, fact, r, 3, m)
            content.insert(1, _f(r.choice(b["claims"][fact.ftype]), m))
            core = article(b, "brief", r, m, content, "")
            for i in range(3):
                out.add(render(fact, lang, self.rng(fact.fid, lang, "synd", i), label="wire", answer=true,
                               planted=False, tier=None, cid=None, verbatim=core, taken=out.taken(qid)),
                        qid, "syndicated", label="wire", slot=i)
        # T1 paraphrase campaign
        cid = f"{qid}-T1-neutral"
        for s in range(N_PLANTED):
            out.add(self.planted(fact, lang, "T1", s, cid, qtext, taken=out.taken(qid)), qid, "planted", "T1",
                    "neutral", s)
        # T0 copy-paste campaign on a domain family
        cid = f"{qid}-T0-neutral"
        r = self.rng(fact.fid, lang, "T0-core")
        stem = safe_name(r, make_place, fact_banned(fact))
        b = bank(lang)
        m = fmap(fact, lang, fact.answer(lang, planted=True))
        content = _ctx(b, fact, r, 4, m)
        content.insert(1, _f(r.choice(b["claims"][fact.ftype]), m))
        core = article(b, r.choice(b["genres"]), r, m, content, stem.en)
        for s in range(N_PLANTED):
            out.add(self.planted(fact, lang, "T0", s, cid, qtext, family=(stem, s), verbatim=core), qid, "planted", "T0", "neutral", s)
        # T3 cross-lingual campaign (alternating languages)
        cid = f"{qid}-T3-neutral"
        for s in range(N_PLANTED):
            pl = lang if s % 2 == 0 else other
            if pl != lang and self._use_llm("T3", lang):
                # write the campaign page in the question's language, then rewrite it into the other one
                src = self.planted(fact, lang, "T3", s, cid, qtext, variant=1)
                p = self._translate(fact, src, pl, s, cid, out.taken(qid)) or self.planted(
                    fact, pl, "T3", s, cid, qtext, taken=out.taken(qid))
            else:
                p = self.planted(fact, pl, "T3", s, cid, qtext, taken=out.taken(qid))
            out.add(p, qid, "planted", "T3", "neutral", s)
        if t4:
            self._t4(fact, lang, out, qid, qtext)

    def _translate(self, fact, page, pl, s, cid, taken=None):
        target = fact.answer(pl, planted=True)
        try:
            res = self.llm.json(translate_messages(page["title"], page["body"], target, pl),
                                seed=self.rng(fact.fid, "T3tr", s).randint(0, 2**31 - 1))
        except QuotaExhausted:
            self._fail("quota")
            return None
        problem = "bad json" if not res else rewrite_problem(str(res.get("body", "")), pl, target, fact.answer(pl))
        if problem:
            self._fail(problem)
            self.llm.stats.fallbacks += 1
            return None
        page = render(fact, pl, self.rng(fact.fid, pl, "T3", s), label="neutral", answer=target, planted=True,
                      tier="T3", cid=cid, taken=taken,
                      llm_content=(str(res.get("title") or page["title"]),
                                   [x.strip() for x in str(res["body"]).split("\n") if x.strip()]))
        page["_gen"] = "llm"
        return page

    def _t4(self, fact, lang, out, qid, qtext):
        cid, ans, chosen = f"{qid}-T4-neutral", fact.answer(lang, planted=True), []
        for s in range(N_PLANTED):
            cands = []
            for c in range(T4_CANDIDATES):
                p = self.planted(fact, lang, "T4", s, cid, qtext, rng=self.rng(fact.fid, lang, "T4", s, c),
                                 taken=out.taken(qid), variant=c)
                if not claim_survives(p["body"], ans, fact.answer(lang)):
                    continue
                if p.get("_gen") == "llm":
                    try:
                        v = self.verifier.json(verify_messages(qtext, ans, p["body"]), seed=1000 * s + c)
                    except QuotaExhausted:
                        v = {"asserts": True}  # already passed the deterministic claim checks
                        self._fail("quota")
                    if not (v and v.get("asserts") is True):
                        continue
                cands.append(p)
            if not cands:
                raise RuntimeError(f"held-out T4: no candidate survived for {qid} slot {s}")
            i = embed.pick_least_similar(chosen, [c["body"] for c in cands])
            chosen.append(cands[i]["body"])
            out.add(cands[i], qid, "planted", "T4", "neutral", s)


def run(seed: int, backend: str, model: str, out_dir: Path, llm_tiers=("T1", "T3", "T4"),
        llm_langs=("en", "ur"), max_calls: int | None = None) -> dict:
    if backend == "llm" and not keys_present(model):
        sys.exit(f"--backend llm needs an API key for {model} in .env")
    facts, split, urdu, _ = build_world(seed)
    test = [f for f in facts if split[f.fid] == "test"]
    t4_ids = {f.fid for f in test if f.regime == "known"}
    t4_ids = set(sorted(t4_ids)[:N_T4_QUESTIONS])
    gen = HeldoutGenerator(seed, backend, model, llm_tiers, llm_langs, max_calls)
    out = BankWriter()
    for f in test:
        gen.fact_pages(f, "en", out, f.fid, question(f, "en", "test")["question"], f.fid in t4_ids)
        if f.fid in urdu:
            gen.fact_pages(f, "ur", out, f.fid + "-ur", question(f, "ur", "test")["question"], False)
        if gen.llm:
            print(f"[progress] {f.fid} done; llm calls={gen.llm.stats.calls} cache_hits={gen.llm.stats.cache_hits}"
                  f" exhausted={gen.llm.exhausted}", flush=True)
    pages_dir = out_dir / "pages"
    write_jsonl(pages_dir / "pages.jsonl", out.pages)
    write_jsonl(pages_dir / "index.jsonl", out.index)
    manifest = {"generator": "heldout", "seed": seed, "backend": backend, "model": model if backend == "llm" else None,
                "template_bank": "data/heldout/templates_{en,ur}.json", "embedder_t4": embed.backend_name(),
                "questions_covered": {"en_test": len(test), "ur_test": len([f for f in test if f.fid in urdu]),
                                      "t4": sorted(t4_ids)},
                "counts": {"pages": len(out.pages)}, "roles": _role_counts(out.index),
                "llm_stats": gen.llm.stats.__dict__ if gen.llm else None,
                "llm_scope": {"tiers": sorted(llm_tiers), "langs": sorted(llm_langs)} if backend == "llm" else None,
                "written_by": _gen_counts(out.index), "llm_rejections": gen.reasons or None}
    (pages_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--backend", choices=["offline", "llm"], default="offline")
    ap.add_argument("--model", default="groq/openai/gpt-oss-120b")
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--llm-tiers", nargs="*", default=["T1", "T3", "T4"], choices=["T1", "T3", "T4"])
    ap.add_argument("--llm-langs", nargs="*", default=["en", "ur"], choices=["en", "ur"])
    ap.add_argument("--max-calls", type=int, default=None, help="stop making new LLM calls after N (free tiers)")
    a = ap.parse_args(argv)
    m = run(a.seed, a.backend, a.model, a.out, a.llm_tiers, a.llm_langs, a.max_calls)
    print(json.dumps({k: m[k] for k in ("counts", "roles")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
