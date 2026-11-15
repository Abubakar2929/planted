# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Per-page answer extraction, shared by Guard and the page-vote baseline (PLAN.md §8, plan-v2.2 Step 2).

    extract_answers(query, results, lang, method="rules") -> one dict per result, in order:
        {"answer": str | None, "answer_norm": str | None,
         "hedge_level": "none" | "may" | "preliminary" | "disagree", "evidence": str (<= 200 chars)}

method="rules" (offline, default): infer the expected answer type from the query wording, find typed
candidate spans in title + snippet + content, keep the one in the sentence sharing the most content
words with the query, normalise it. None when no sentence about the query holds a typed candidate.

method="llm": one batched call per query through planted.agent.cache.call_model_cached (temperature 0,
seed 0); falls back to rules when the reply does not parse.

Hedge level: data/lexicons detect_hedge on the sentence holding the answer.
Only the visible result keys (url, title, snippet, content) are read; hidden Page fields never are.
"""

from __future__ import annotations

import json
import re
import unicodedata

from data.lexicons.lexicon import ORDER as HEDGE_LEVELS
from data.lexicons.lexicon import detect_hedge
from data.lexicons.lexicon import normalise as lex_normalise

ANSWER_TYPES = ("year", "phone", "date", "money", "number", "person", "place", "name")
EVIDENCE_CHARS = 200
LLM_CONTENT_CHARS = 1200
LLM_MAX_TOKENS = 1200

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_DIGITS = str.maketrans({
    **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic
    **{chr(0x06F0 + i): str(i) for i in range(10)},  # Extended Arabic-Indic (Urdu)
    "٬": ",",  # Arabic thousands separator
    "٫": ".",  # Arabic decimal separator
    "−": "-",  # minus sign
    "–": "-", "—": "-",
})

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
    "جنوری": 1, "فروری": 2, "مارچ": 3, "اپریل": 4, "مئی": 5, "جون": 6, "جولائی": 7,
    "اگست": 8, "ستمبر": 9, "اکتوبر": 10, "نومبر": 11, "دسمبر": 12,
}
_MULTIPLIERS = {
    "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000,
    "ہزار": 1_000, "لاکھ": 100_000, "کروڑ": 10_000_000, "ملین": 1_000_000, "ارب": 1_000_000_000,
}


def clean_text(text: str) -> str:
    """NFKC, ZWNJ/ZWJ stripped, Urdu/Arabic-Indic digits -> ASCII. Case and spacing kept."""
    t = unicodedata.normalize("NFKC", text or "")
    return t.replace("‌", "").replace("‍", "").replace("‏", "").translate(_DIGITS)


def _num_value(num: str, mult: str | None = None) -> str | None:
    s = num.replace(",", "").replace(" ", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if mult:
        v *= _MULTIPLIERS.get(mult.lower(), 1)
    if v == int(v):
        return str(int(v))
    return f"{v:.6f}".rstrip("0").rstrip(".")


def _norm_date(text: str) -> str | None:
    t = clean_text(text).lower()
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    month_alt = "|".join(sorted(map(re.escape, MONTHS), key=len, reverse=True))
    m = re.search(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_alt})\.?,?\s+(\d{{4}})", t)
    if m:
        return f"{int(m[3]):04d}-{MONTHS[m[2]]:02d}-{int(m[1]):02d}"
    m = re.search(rf"({month_alt})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", t)
    if m:
        return f"{int(m[3]):04d}-{MONTHS[m[1]]:02d}-{int(m[2]):02d}"
    return None


def normalize_answer(answer: str | None, atype: str, lang: str = "en") -> str | None:
    """Canonical form for comparing answers: phone -> digits, number -> no separators,
    year -> 4 digits, date -> YYYY-MM-DD, names -> folded lower case."""
    if answer is None:
        return None
    t = clean_text(answer).strip()
    if not t:
        return None
    if atype == "phone":
        d = re.sub(r"\D", "", t)
        return d or None
    if atype == "year":
        m = re.search(r"(?<!\d)(\d{4})(?!\d)", t)
        return m[1] if m else None
    if atype == "date":
        return _norm_date(t) or lex_normalise(t, lang)
    if atype in ("number", "money"):
        m = re.search(rf"(-?\d[\d,]*(?:\.\d+)?)\s*({'|'.join(_MULTIPLIERS)})?", t, re.I)
        if m:
            neg = m[1].startswith("-")
            v = _num_value(m[1].lstrip("-"), m[2])
            if v is not None:
                return ("-" + v) if neg and v != "0" else v
        return None
    t = lex_normalise(t, lang)
    t = re.sub(r"[^\w\s'-]", " ", t)
    t = re.sub(r"^(the|a|an)\s+", "", t.strip())
    return re.sub(r"\s+", " ", t).strip() or None


# ---------------------------------------------------------------------------
# Query -> expected answer type
# ---------------------------------------------------------------------------

_TYPE_RULES_EN: list[tuple[str, str]] = [
    ("phone", r"phone|helpline|hotline|contact number|telephone|call centre|call center|number to call"),
    ("date", r"\bwhat date\b|\bwhich date\b|\bon what day\b|\bexact date\b|\bdate (?:did|was|of)\b"),
    ("year", r"\bwhich year\b|\bwhat year\b|\byear (?:was|did)\b|\bwhen was\b.*\b(?:founded|established|set up|formed|created|built|opened|incorporated|started)\b|\bwhen did\b.*\b(?:found|establish|form|start)\b"),
    ("money", r"\bhow much\b.*\b(?:cost|pay|charge|price|worth|spend|spent)\b|\bcost\b|\bprice\b|\bbudget\b|\bfee\b|\brevenue\b|\bsalary\b"),
    ("number", r"\bhow (?:many|much|long|tall|high|far|deep|wide|big|large|old|heavy)\b|\bpopulation\b|\bnumber of\b|\bpercentage\b|\bin (?:metres|meters|kilometres|km|feet)\b"),
    ("person", r"^\s*who\b|\bwhose\b|\bwhich person\b|\bname of the (?:first |current )?(?:director|founder|head|chair|mayor|president)"),
    ("place", r"\bwhere\b|\bwhich (?:city|town|village|country|district|region|place)\b|\bwhat (?:city|town|village|country)\b|\bheadquartered\b|\bbased\b|\blocated\b"),
]
_TYPE_RULES_UR: list[tuple[str, str]] = [
    ("phone", r"فون|ہیلپ ?لائن|رابطہ نمبر|رابطے کا نمبر|ٹیلی ?فون|کسٹمر سپورٹ|کسٹمر کیئر"),
    ("date", r"کس تاریخ|کون سی تاریخ|کونسی تاریخ|تاریخ کو"),
    ("year", r"کس سال|کون سے سال|کونسے سال|کس سن|کب قائم|کب بنا|کب بنی|کب شروع|کب کھول|قیام کب"),
    ("money", r"قیمت|لاگت|کتنے روپے|کتنی رقم|فیس|بجٹ"),
    ("number", r"کتنے|کتنی|کتنا|آبادی|لمبائی|اونچائی|بلندی|تعداد|میٹر"),
    ("person", r"کون تھ|کون ہ|کس نے|کس کو"),
    ("place", r"کہاں|کس شہر|کس قصبے|کس قصبہ|کس گاؤں|کس ملک|کس علاقے"),
]


def infer_answer_type(query: str, lang: str = "en") -> str:
    """year | phone | date | money | number | person | place | name (default)."""
    q = clean_text(query)
    rules = _TYPE_RULES_UR if lang == "ur" or re.search(r"[؀-ۿ]", q) else _TYPE_RULES_EN
    ql = q.lower()
    for atype, pat in rules:
        if re.search(pat, ql):
            return atype
    return "name"


# ---------------------------------------------------------------------------
# Query content words (entity overlap)
# ---------------------------------------------------------------------------

_STOP_EN = set("""
a an the of in on at to for from by with and or is are was were be been being what which who whom whose
when where how many much long tall high far deep big large old did does do its it this that these those
year date number name first current exact exactly called recorded have has had there their in into
about as than per since metres meters metre meter kilometres km feet
""".split())
_STOP_UR = set("""
کا کی کے میں سے کو نے پر اور یا ہے ہیں تھا تھی تھے ہو گیا گئی گئے کیا کیسے کون کونسا کونسی کس کب کہاں
کتنے کتنی کتنا کیا یہ وہ ایک بھی تک لیے لئے جو جس جن ان اس سال تاریخ نمبر نام پہلے پہلا پہلی
""".split())

# Words that signal the predicate of each type; a sentence mentioning one is about the asked fact.
_CUES = {
    "year": r"found|establish|set up|formed|creat|built|open|incorporat|start|since|came into being|origin|inception|dates? back|charter|\bbeg[au]n\b|first (?:met|meeting)|قائم|بنا|بنی|شروع|بنیاد",
    "date": r"open|launch|inaugurat|held|took place|began|start|کھول|افتتاح|شروع",
    "phone": r"phone|call|helpline|hotline|contact|support|ring|dial|فون|رابط|ہیلپ|کال",
    "money": r"cost|price|budget|fee|paid|spent|worth|قیمت|لاگت",
    "number": r"",
    "person": r"director|founder|head|led|chair|curator|president|mayor|appointed|ڈائریکٹر|سربراہ|بانی",
    "place": r"headquarter|\bbased?\b|located|offices?\b|situated|home to|\bmeets?\b|(?:works?|operates?|runs?) (?:out of|from)|(?:workshop|premises|base) in|ہیڈ ?کوارٹر|واقع|مرکز|قائم|دفتر",
    "name": r"",
}


_SUFFIXES = ("ations", "ation", "ings", "ing", "edly", "ed", "es", "s", "e", "y")


def _stem(tok: str) -> str:
    """Light suffix stripping (founded/founding -> found); keeps community != commute."""
    for suf in _SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def _tokens(text: str, lang: str) -> list[str]:
    t = lex_normalise(clean_text(text), lang)
    return re.findall(r"[\w']+", t)


def query_terms(query: str, lang: str) -> set[str]:
    stop = _STOP_UR if lang == "ur" else _STOP_EN
    return {_stem(t) for t in _tokens(query, lang) if t not in stop and len(t) > 1 and not t.isdigit()}


def _unit_words(query: str, atype: str, lang: str) -> list[str]:
    """Words expected right after a number of the asked kind, e.g. 'metres', 'species', 'residents'."""
    if atype != "number":
        return []
    ql = clean_text(query).lower()
    if re.search(r"\bby how much\b|\bpercent|\bper cent\b|\bshare of\b|\bproportion\b|\brate\b|فیصد", ql):
        return ["%", "perce", "per c", "فیصد"]
    units: list[str] = []
    m = re.search(r"\bin (metres|meters|kilometres|kilometers|km|feet|miles|hectares|years)\b", ql)
    if m:
        units.append(m[1][:5])
    m = re.search(r"\bhow many ([a-z]+)(?: ([a-z]+))?", ql)
    if m:
        units += [w[:5] for w in m.groups() if w and w not in _STOP_EN]
    if re.search(r"\bhow (long|tall|high|deep|wide|far)\b", ql) and not units:
        units += ["metre", "meter", "km", "kilom", "feet", "miles"]
    if "population" in ql or "آبادی" in ql:
        units += ["resid", "peopl", "inhab", "citiz", "souls", "افراد", "لوگ", "باشند", "نفوس"]
    if re.search(r"میٹر", ql):
        units.append("میٹر")
    return units


# ---------------------------------------------------------------------------
# Typed candidate spans
# ---------------------------------------------------------------------------

_MONTH_ALT = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
_RE_PHONE = re.compile(r"(?<![\w+])\+?\d[\d\s().\-]{5,}\d(?!\w)")
_RE_DATE = re.compile(
    rf"(?<!\d)(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTH_ALT})\.?,?\s+\d{{4}}"
    rf"|(?:{_MONTH_ALT})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}})(?!\d)",
    re.I,
)
_RE_YEAR = re.compile(r"(?<![\d,.\-])(1[0-9]\d\d|20\d\d)(?!\d|,\d|\.\d)")
_RE_NUMBER = re.compile(
    rf"(?<![\w.,])(-?\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|-?\d+(?:\.\d+)?)(?:\s*({'|'.join(_MULTIPLIERS)}))?(?!\w|,\d|\.\d)",
    re.I,
)
_RE_MONEY = re.compile(
    r"(?:[$£€₨]|rs\.?|pkr|usd|eur|gbp|روپے)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:thousand|million|billion))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:thousand|million|billion)?\s*(?:dollars|pounds|euros|rupees|روپے)",
    re.I,
)
_CAP_TOKEN = r"[A-Z][a-zA-Z'’\-]+"
_RE_CAPSPAN = re.compile(rf"{_CAP_TOKEN}(?:\s+(?:of|de|van|von|al|la|le|du)\s+{_CAP_TOKEN}|\s+{_CAP_TOKEN})*")
_CAP_STOP = set("""
The A An It Its This That These Those There Their They He She His Her We Our You Your I In On At For From By
With And Or But As If When While After Before Since During Today Yesterday Now Some Many Most Every Each All
According Local Residents Officials Measured Engineers Historians Records Sources Reports Ask Follow Sign Comments
Print Questions Got Read More Update Updates Advertisement Note Notes Yes No Under Over Among Across Near
Inside Outside Between Around Along Through Despite Following Unlike Like Members Monday Tuesday Wednesday Thursday
Friday Saturday Sunday January February March April May June July August September October November December
""".split())
_PLACE_PREPS = re.compile(r"(?:\bin|\bat|\bto|\bnear|\bfrom|\bbased in|\bheadquartered in|\blocated in|\btown of|\bcity of|\bvillage of)\s*$", re.I)

_CONNECTORS = {"of", "de", "van", "von", "al", "la", "le", "du"}
# Types whose answer sentence must mention the asked predicate (founded, based, director, ...).
CUE_REQUIRED = {"year", "place", "person"}

_SENT_SPLIT =re.compile(r"(?<=[.!?۔؟])\s+|\n+")
_ABBREV_END = re.compile(r"\b(?:Ltd|Inc|Co|Dr|Mr|Mrs|Ms|St|Mt|No|Corp|Jr|Sr|vs|approx)\.$")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(text) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        if out and _ABBREV_END.search(out[-1]):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def _candidates(sent: str, atype: str, qterms: set[str], lang: str) -> list[tuple[str, int]]:
    """(span, start offset) of every typed candidate in one sentence."""
    if atype == "phone":
        return [(m[0].strip(), m.start()) for m in _RE_PHONE.finditer(sent) if len(re.sub(r"\D", "", m[0])) >= 7]
    if atype == "date":
        return [(m[0], m.start()) for m in _RE_DATE.finditer(sent)]
    if atype == "year":
        return [(m[1], m.start()) for m in _RE_YEAR.finditer(sent)]
    if atype == "money":
        out = [(m[0], m.start()) for m in _RE_MONEY.finditer(sent)]
        return out or _candidates(sent, "number", qterms, lang)
    if atype == "number":
        # Phone numbers and dates are not quantities: blank them first.
        masked = _RE_PHONE.sub(lambda m: " " * len(m[0]), sent)
        masked = _RE_DATE.sub(lambda m: " " * len(m[0]), masked)
        out = []
        for m in _RE_NUMBER.finditer(masked):
            span = m[0]
            if span.startswith("-") and m.start() > 0 and not masked[m.start() - 1].isspace():
                span = span[1:]
            out.append((span.strip(), m.start() + (len(m[0]) - len(span))))
        return out
    if lang == "ur" or re.search(r"[؀-ۿ]", sent):
        return _ur_name_candidates(sent, qterms)
    out = []
    for m in _RE_CAPSPAN.finditer(sent):
        toks = m[0].split()
        start = m.start()
        while toks and toks[0] in _CAP_STOP:  # sentence-initial / function capitals
            start += len(toks[0]) + 1
            toks = toks[1:]
        while toks and (toks[0] in _CONNECTORS or toks[0] in _CAP_STOP):
            start += len(toks[0]) + 1
            toks = toks[1:]
        while toks and (toks[-1] in _CAP_STOP or toks[-1] in _CONNECTORS):
            toks = toks[:-1]
        if not toks:
            continue
        span = " ".join(toks)
        span_terms = {_stem(t) for t in _tokens(span, lang)}
        if span_terms & qterms:  # part of the asked-about entity, not the answer
            continue
        out.append((span, start))
    return out


def _ur_name_candidates(sent: str, qterms: set[str]) -> list[tuple[str, int]]:
    """Urdu has no capitals: runs of up to 3 tokens that are neither query words nor function words."""
    out = []
    run: list[tuple[str, int]] = []
    for m in re.finditer(r"[\w']+", sent):
        tok = m[0]
        bad = tok in _STOP_UR or _stem(lex_normalise(tok, "ur")) in qterms or tok.isdigit() \
            or re.search(_CUES["person"] + "|" + _CUES["place"], tok)
        if bad:
            if run:
                out.append(run)
            run = []
        else:
            run.append((tok, m.start()))
    if run:
        out.append(run)
    return [(" ".join(t for t, _ in r[:3]), r[0][1]) for r in out if r]


ANAPHORA_BASE = 5


def _unit_follows(sent: str, span: str, pos: int, units: list[str]) -> bool:
    after = sent.lower()[pos + len(span): pos + len(span) + 24].strip()
    return any(after.startswith(u) for u in units)


def _candidate_score(sent: str, span: str, pos: int, atype: str, units: list[str], lang: str) -> float:
    s = 0.0
    low = sent.lower()
    after = low[pos + len(span): pos + len(span) + 24].strip()
    before = sent[max(0, pos - 24): pos]
    if atype == "number":
        if _unit_follows(sent, span, pos, units):
            s += 3
        val = re.sub(r"[^\d]", "", span)
        if re.fullmatch(r"(1[5-9]|20)\d\d", val) and "," not in span and not any(after.startswith(u) for u in units):
            s -= 2  # bare 4-digit years are rarely the quantity asked for
        if re.match(r"(%|percent|per cent)", after) and "%" not in units:
            s -= 1
    if atype in ("place", "name") and _PLACE_PREPS.search(before):
        s += 2
    if atype == "person":
        if len(span.split()) >= 2:
            s += 1
        if re.search(r"(?:was|is|by|director|founder|head|named)\s*,?\s*$", before, re.I):
            s += 1
    if atype == "place" and len(span.split()) > 3:
        s -= 1
    # closeness to the predicate cue
    cue = _CUES.get(atype)
    if cue:
        cm = [c.start() for c in re.finditer(cue, low)]
        if cm:
            s += 1.0 / (1 + min(abs(c - pos) for c in cm) / 40)
    return s


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _page_text(r: dict) -> str:
    return "\n".join(clean_text(r.get(k) or "") for k in ("title", "snippet", "content"))


def _extract_one(query: str, r: dict, lang: str, atype: str, qterms: set[str], units: list[str]) -> dict:
    sents = _dedupe(split_sentences(_page_text(r)))
    cue = _CUES.get(atype) or None
    best: tuple[float, str, str] | None = None  # (score, span, sentence)
    best_ctx: tuple[int, str] | None = None
    overlaps = [len({_stem(t) for t in _tokens(s, lang)} & qterms) for s in sents]
    page_on_topic = any(overlaps)
    for sent, overlap in zip(sents, overlaps):
        has_cue = bool(cue and re.search(cue, sent.lower()))
        if overlap and (best_ctx is None or overlap > best_ctx[0]):
            best_ctx = (overlap, sent)
        if atype in CUE_REQUIRED and not has_cue:
            continue
        # A sentence without query words ("The structure measures 1,616 metres") only counts for
        # quantities followed by the asked unit, on a page that names the entity elsewhere.
        if overlap == 0 and not (atype == "number" and units and page_on_topic):
            continue
        for span, pos in _candidates(sent, atype, qterms, lang):
            unit_ok = _unit_follows(sent, span, pos, units)
            if overlap == 0 and not unit_ok:
                continue
            # "A meeting in Darford drew 16 people": one shared word (the place) is not enough for a
            # quantity that lacks the asked unit.
            if atype == "number" and units and not unit_ok and overlap < min(2, len(qterms)):
                continue
            base = overlap * 10 if overlap else ANAPHORA_BASE
            sc = base + (2 if has_cue else 0) + _candidate_score(sent, span, pos, atype, units, lang)
            if best is None or sc > best[0]:
                best = (sc, span, sent)
    if best is not None and _confident(best[0], atype, units, qterms):
        _, span, sent = best
        return {
            "answer": span,
            "answer_norm": normalize_answer(span, atype, lang),
            "hedge_level": detect_hedge(sent, lang),
            "evidence": sent[:EVIDENCE_CHARS],
        }
    sent = best_ctx[1] if best_ctx else ""
    return {"answer": None, "answer_norm": None,
            "hedge_level": detect_hedge(sent, lang) if sent else "none",
            "evidence": sent[:EVIDENCE_CHARS]}


def _confident(score: float, atype: str, units: list[str], qterms: set[str]) -> bool:
    # Either one shared content word (base 10) or a unit-matched anaphoric quantity (base 5 + 3).
    return score >= ANAPHORA_BASE + 3


def _extract_rules(query: str, results: list[dict], lang: str) -> list[dict]:
    atype = infer_answer_type(query, lang)
    qterms = query_terms(query, lang)
    units = _unit_words(query, atype, lang)
    return [_extract_one(query, r, lang, atype, qterms, units) for r in results]


# ---------------------------------------------------------------------------
# LLM method (one batched call per query)
# ---------------------------------------------------------------------------

LLM_SYSTEM = (
    "You read search results and report, for each page, the answer that page itself asserts to the "
    "question. Do not judge whether the page is right. Reply with JSON only."
)


def build_llm_messages(query: str, results: list[dict], lang: str) -> list[dict]:
    blocks = []
    for i, r in enumerate(results, start=1):
        content = clean_text(r.get("content") or r.get("snippet") or "")[:LLM_CONTENT_CHARS]
        blocks.append(f"[id={i}] {clean_text(r.get('title') or '')}\n{content}")
    user = (
        f"Question ({lang}): {query}\n\nPages:\n\n" + "\n\n".join(blocks) + "\n\n"
        "For every page id, give the short answer the page states to the question (copy the value as "
        "written, e.g. a year, number, phone number, date or name), or null if the page does not state "
        "one. Also give the page's hedge on that answer: \"none\", \"may\" (possibly, reportedly), "
        "\"preliminary\" (early or unconfirmed results) or \"disagree\" (the page disputes it).\n"
        'Return a JSON list: [{"id": 1, "answer": "..." or null, "hedge": "none"}, ...]'
    )
    return [{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}]


def parse_llm_reply(text: str, n: int) -> list[dict] | None:
    """{id, answer, hedge} list -> n dicts (index = id-1); None if the reply is not usable JSON."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text).strip()
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j <= i:
        return None
    try:
        data = json.loads(t[i: j + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out: list[dict] = [{"answer": None, "hedge": None} for _ in range(n)]
    seen = False
    for pos, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("id", pos + 1)) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= idx < n:
            continue
        ans = item.get("answer")
        if ans is not None and not isinstance(ans, str):
            ans = str(ans)
        if isinstance(ans, str) and ans.strip().lower() in ("", "null", "none", "n/a", "unknown"):
            ans = None
        hedge = item.get("hedge")
        out[idx] = {"answer": ans.strip() if ans else None,
                    "hedge": hedge if hedge in HEDGE_LEVELS else None}
        seen = True
    return out if seen else None


def _locate(answer: str, r: dict, lang: str) -> str:
    """Sentence of the page that contains the answer (empty if not found)."""
    a = lex_normalise(clean_text(answer), lang)
    digits = re.sub(r"\D", "", a)
    for sent in split_sentences(_page_text(r)):
        s = lex_normalise(sent, lang)
        if a and a in s:
            return sent
        if len(digits) >= 4 and digits in re.sub(r"\D", "", s):
            return sent
    return ""


def _extract_llm(query: str, results: list[dict], lang: str, llm_model: str) -> list[dict]:
    from planted.agent.cache import call_model_cached

    if not results:
        return []
    try:
        reply = call_model_cached(llm_model, build_llm_messages(query, results, lang), seed=0,
                                  temperature=0, max_tokens=LLM_MAX_TOKENS)
        parsed = parse_llm_reply(reply.get("content") or "", len(results))
    except Exception:  # noqa: BLE001 - any API/parse failure falls back to the offline rules
        parsed = None
    if parsed is None:
        return _extract_rules(query, results, lang)
    atype = infer_answer_type(query, lang)
    out = []
    for r, p in zip(results, parsed):
        ans = p["answer"]
        sent = _locate(ans, r, lang) if ans else ""
        hedge = detect_hedge(sent, lang) if sent else (p["hedge"] or "none")
        out.append({
            "answer": ans,
            "answer_norm": normalize_answer(ans, atype, lang) if ans else None,
            "hedge_level": hedge,
            "evidence": (sent or (ans or ""))[:EVIDENCE_CHARS],
        })
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_answers(query: str, results: list[dict], lang: str, method: str = "rules",
                    llm_model: str = "gflite31") -> list[dict]:
    """One {answer, answer_norm, hedge_level, evidence} dict per result, in order."""
    if method == "rules":
        return _extract_rules(query, results, lang)
    if method == "llm":
        return _extract_llm(query, results, lang, llm_model)
    raise ValueError(f"unknown extraction method {method!r}; expected 'rules' or 'llm'")
