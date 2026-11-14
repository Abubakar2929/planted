# OWNER: B — see PLAN.md §2
"""Render Contract-1 Page dicts from a template bank (main generator).

Every page, in every tier, gets a randomised outlet, domain, author, date, boilerplate, genre, length
and sentence order (PLAN.md firewall rule (a)). A campaign's pages share only what a real campaign
would: the claim, plus, in T0 only, a verbatim core paragraph and a domain-family stem.
"""

from __future__ import annotations

import json
import random
import re
from functools import cache
from pathlib import Path

from data.generator.world import (
    ENTITY_KINDS,
    FACT_TYPES,
    Fact,
    HedgeClaim,
    Name,
    fact_banned,
    make_person,
    make_place,
    safe_name,
)

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

# T0 campaigns reuse one name stem across a family of domains (the Pravda-network pattern).
T0_DOMAIN_FAMILY = ["{s}-news", "{s}daily", "{s}24", "{s}-today", "{s}-post", "{s}info", "{s}-online",
                    "{s}now", "{s}-wire", "{s}-report"]
T0_OUTLET_FAMILY = ["{S} News", "{S} Daily", "{S} 24", "{S} Today", "{S} Post", "{S} Info",
                    "{S} Online", "{S} Now", "{S} Wire", "{S} Report"]
T0_OUTLET_FAMILY_UR = ["{S} نیوز", "روزنامہ {S}", "{S} 24", "{S} آج", "{S} پوسٹ", "{S} انفو",
                       "{S} آن لائن", "{S} ابھی", "{S} وائر", "{S} رپورٹ"]


@cache
def load_bank(name: str, lang: str, root: str | None = None) -> dict:
    base = Path(root) if root else TEMPLATES
    return json.loads((base / f"{name}_{lang}.json").read_text(encoding="utf-8"))


def ascii_stem(name: Name) -> str:
    return re.sub(r"[^a-z]", "", name.en.lower())


def _iso_date(rng: random.Random) -> str:
    return f"{rng.randint(2015, 2026)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def _handle(person: Name, rng: random.Random) -> str:
    first = person.en.split()[0].lower()
    return f"{first}_{rng.choice(['notes', 'writes', 'online', 'daily', ''])}{rng.randint(1, 99)}".replace("__", "_")


def fill_map(fact: Fact, lang: str, answer: str | None) -> dict:
    pick = (lambda n: n.en) if lang == "en" else (lambda n: n.ur)
    m = {
        "E": fact.entity_text(lang), "R": pick(fact.region), "N": pick(fact.neighbour),
        "P": pick(fact.person), "P2": pick(fact.person2), "V": pick(fact.river),
        "Y": str(fact.year_ctx), "C": str(fact.num_ctx),
    }
    if answer is not None:
        m["A"] = answer
    return m


def fmt(template: str, m: dict) -> str:
    out = template
    for k in sorted(m, key=len, reverse=True):
        out = out.replace("{" + k + "}", m[k])
    return out


class Outlet:
    """A randomised source: name, domain, author, date, and the label's boilerplate."""

    def __init__(self, bank: dict, label: str, rng: random.Random, lang: str, fact_map: dict,
                 stem: Name | None = None, family_idx: int | None = None,
                 banned: set[str] | None = None, taken: set[str] | None = None):
        """banned: answer strings no outlet/author name may contain; taken: domains already used by
        this question's pages (a fresh random outlet is redrawn until its domain is new)."""
        self.label = label
        self.lang = lang
        banned = banned or set()
        spec = bank["labels"][label]
        fixed_stem = stem is not None
        for _ in range(200):
            stem_i = stem if fixed_stem else safe_name(rng, make_place, banned)
            stem_txt = stem_i.en if lang == "en" else stem_i.ur
            s = ascii_stem(stem_i)
            if family_idx is not None:  # T0 domain family
                fam = T0_OUTLET_FAMILY if lang == "en" else T0_OUTLET_FAMILY_UR
                self.name = fam[family_idx % len(fam)].replace("{S}", stem_txt)
                self.domain = T0_DOMAIN_FAMILY[family_idx % len(T0_DOMAIN_FAMILY)].replace("{s}", s) + ".example"
            elif label == "official":
                self.name = spec["outlet"][0].replace("{E}", fact_map["E"])
                self.domain = spec["domain"][0].replace("{s}", s)
            else:  # name and domain drawn as a matched pair, as on real sites
                i = rng.randrange(len(spec["outlet"]))
                self.name = spec["outlet"][i].replace("{S}", stem_txt)
                self.domain = spec["domain"][i % len(spec["domain"])].replace("{s}", s)
            if fixed_stem or taken is None or self.domain not in taken:
                break
        if taken is not None:
            taken.add(self.domain)
        a1, a2 = safe_name(rng, make_person, banned), safe_name(rng, make_person, banned)
        self.author_name = a1.en if lang == "en" else a1.ur
        self.handle = _handle(a1, rng)
        sub = {"O": self.name, "AU": self.author_name, "AU2": a2.en if lang == "en" else a2.ur,
               "au": self.handle, "E": fact_map.get("E", ""), "R": fact_map.get("R", "")}
        self.header = fmt(rng.choice(spec["header"]), sub)
        self.byline = fmt(rng.choice(spec["byline"]), sub)
        self.footer = fmt(rng.choice(spec["footer"]), sub)
        self.extra = list(spec.get("extra", []))
        self.author = None if label == "official" or rng.random() < 0.12 else (
            self.handle if label == "blog" else self.author_name)
        self.date = None if rng.random() < 0.08 else _iso_date(rng)


def _slug(text: str, rng: random.Random) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())[:5] or ["page"]
    return "-".join(words) + f"-{rng.randint(100, 9999)}"


def assemble(outlet: Outlet, bank: dict, rng: random.Random, title: str, content: list[str],
             fmap: dict, verbatim: bool = False) -> str:
    """Return the page body. Content order is already decided by the caller.

    verbatim=True: `content` is a whole copied article (T0 copy-paste, wire syndication), so only the
    site chrome (header, byline, boilerplate, footer) is added around it."""
    genre = rng.choice(bank["genres"])
    framed = outlet.label != "official" and not verbatim  # official sites have no news-genre framing
    lines = [outlet.header]
    if rng.random() < 0.6:
        lines.append(rng.choice(bank["boilerplate"]))
    lines.append(title)
    lines.append(outlet.byline)
    if framed:
        lines.append(fmt(rng.choice(genre["open"]), fmap))
    if outlet.extra and not verbatim and rng.random() < 0.8:
        lines.append(rng.choice(outlet.extra))
    lines.extend(content)
    if framed:
        lines.append(fmt(rng.choice(genre["close"]), fmap))
    for _ in range(rng.randint(0, 2)):
        lines.append(rng.choice(bank["boilerplate"]))
    lines.append(outlet.footer)
    return "\n".join(lines)


def _context(bank: dict, fact: Fact, rng: random.Random, n: int, fmap: dict) -> list[str]:
    """Pick n background facts, each in one randomly chosen phrasing (groups of variants)."""
    kind = FACT_TYPES[fact.ftype]
    groups = bank["context"]["generic"] + bank["context"].get(kind, [])
    return [fmt(rng.choice(g) if isinstance(g, list) else g, fmap)
            for g in rng.sample(groups, min(n, len(groups)))]


def make_page(*, fact: Fact, bank: dict, lang: str, rng: random.Random, label: str, role: str,
              planted: bool, campaign_id: str | None, tier: str | None, answer: str | None,
              stem: Name | None = None, family_idx: int | None = None,
              core: list[str] | None = None, title_kind: str | None = None,
              content_override: list[str] | None = None, title_override: str | None = None,
              taken: set[str] | None = None) -> dict:
    """role: honest | filler | planted | official | syndicated (layout is the same; content differs).

    content_override / title_override carry LLM-written text; the outlet wrapper stays randomised."""
    fmap = fill_map(fact, lang, answer)
    if label == "official" and stem is None:  # an official site is named after the entity itself
        stem = Name(fact.entity.en.split()[0], fact.entity.ur.split()[0])
    outlet = Outlet(bank, label, rng, lang, fmap, stem=stem, family_idx=family_idx,
                    banned=fact_banned(fact) if fact.regime != "hedge" else set(), taken=taken)
    tk = title_kind or ("planted" if planted else ("filler" if answer is None else "honest"))
    title = title_override or fmt(rng.choice(bank["titles"][tk]), fmap)
    if content_override is not None:  # LLM-written article text
        content = list(content_override)
        sentences = [s for c in content for s in re.split(r"(?<=[.!?۔])\s+", c) if s.strip()]
        claim = next((s for s in sentences if answer and answer in s), sentences[0] if sentences else title)
    elif core is not None:  # a whole copied article (T0 campaign, syndicated wire copy)
        content = list(core)
        claim = next((c for c in core if answer and answer in c), core[0])
    elif answer is None:  # filler: entity context, never the asked fact
        content = _context(bank, fact, rng, rng.randint(4, 7), fmap)
        claim = content[0]
    else:
        claim = fmt(rng.choice(bank["claims"][fact.ftype]), fmap)
        ctx = _context(bank, fact, rng, rng.randint(2, 6), fmap)
        pos = rng.randint(0, min(2, len(ctx)))
        content = ctx[:pos] + [claim] + ctx[pos:]
        if planted and rng.random() < 0.6:
            content.insert(content.index(claim) + 1, rng.choice(bank["planted_frames"]))
    body = assemble(outlet, bank, rng, title, content, fmap, verbatim=core is not None)
    section = rng.choice(bank["sections"])
    url = f"https://{outlet.domain}/{section}/{_slug(fact.entity.en, rng)}"
    snippet = claim if len(claim) <= 220 else claim[:217] + "..."
    return {
        "url": url, "domain": outlet.domain, "title": title, "snippet": snippet, "body": body,
        "lang": lang, "author": outlet.author, "date": outlet.date,
        "planted": planted, "campaign_id": campaign_id, "label": label, "tier": tier,
        "asserted_answer": answer if answer is not None else "none",
        "source_hedge": None if answer is None else "none",
    }


def core_paragraph(fact: Fact, bank: dict, lang: str, rng: random.Random, answer: str,
                   planted: bool = False) -> list[str]:
    """A whole article, copied verbatim across a T0 campaign or a syndicated wire story:
    genre opener, the claim (plus a 'correction' frame if planted), four context sentences, closer."""
    fmap = fill_map(fact, lang, answer)
    genre = rng.choice(bank["genres"])
    claim = fmt(rng.choice(bank["claims"][fact.ftype]), fmap)
    ctx = _context(bank, fact, rng, 4, fmap)
    body = ctx[:1] + [claim] + ([rng.choice(bank["planted_frames"])] if planted else []) + ctx[1:]
    return [fmt(rng.choice(genre["open"]), fmap)] + body + [fmt(rng.choice(genre["close"]), fmap)]


# ---------------------------------------------------------------------------
# Hedge pages (arm D)
# ---------------------------------------------------------------------------

def make_hedge_page(*, claim: HedgeClaim, bank: dict, lang: str, rng: random.Random, level: str,
                    label: str = "neutral", taken: set[str] | None = None) -> dict:
    pick = (lambda n: n.en) if lang == "en" else (lambda n: n.ur)
    place = pick(claim.place)
    lake = f"Lake {claim.place.en}" if lang == "en" else f"{claim.place.ur} جھیل"
    answer = claim.answer_en if lang == "en" else claim.answer_ur
    fmap = {"T": place, "L": lake, "Y": str(claim.year), "A": answer, "E": place,
            "R": pick(claim.region), "N": place, "P": pick(claim.person), "P2": pick(claim.person),
            "V": place, "C": str(rng.randint(3, 40))}
    outlet = Outlet(bank, label, rng, lang, fmap, taken=taken)
    title = fmt(rng.choice(bank["hedge_titles"]), fmap)
    sentence = fmt(rng.choice(bank["hedge"][claim.htype][level]), fmap)
    who = f"{pick(claim.person)}" + (" commented on the findings." if lang == "en" else " نے نتائج پر تبصرہ کیا۔")
    content = [sentence, who]
    body = assemble(outlet, bank, rng, title, content, fmap)
    url = f"https://{outlet.domain}/{rng.choice(bank['sections'])}/{_slug(claim.place.en + ' ' + claim.htype, rng)}"
    return {
        "url": url, "domain": outlet.domain, "title": title, "snippet": sentence[:220], "body": body,
        "lang": lang, "author": outlet.author, "date": outlet.date, "planted": False,
        "campaign_id": None, "label": label, "tier": None, "asserted_answer": answer,
        "source_hedge": level,
    }


def make_hedge_filler(*, claim: HedgeClaim, bank: dict, lang: str, rng: random.Random) -> dict:
    """A page about the same town that does not state the finding."""
    fake = Fact(fid=claim.hid, ftype="population", entity=claim.place, answer_en="", answer_ur="",
                planted_en="", planted_ur="", region=claim.region, neighbour=claim.place,
                person=claim.person, person2=claim.person, river=claim.region, year_ctx=claim.year,
                num_ctx=rng.randint(3, 40), regime="hedge")
    page = make_page(fact=fake, bank=bank, lang=lang, rng=rng, label=rng.choice(["neutral", "blog"]),
                     role="filler", planted=False, campaign_id=None, tier=None, answer=None)
    return page


__all__ = ["ENTITY_KINDS", "Outlet", "core_paragraph", "fmt", "load_bank", "make_hedge_filler",
           "make_hedge_page", "make_page"]
