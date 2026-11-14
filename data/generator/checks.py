# OWNER: B — see PLAN.md §2
"""Content rules shared by the generator (to accept or retry an LLM rewrite) and the validator."""

from __future__ import annotations

import re

from data.lexicons.lexicon import detect_hedge

REAL_OUTLETS = re.compile(
    r"\b(reuters|associated press|ap news|bbc|cnn|fox news|al jazeera|aljazeera|pravda|sputnik|russia today|"
    r"new york times|washington post|the guardian|bloomberg|dawn news|geo news|ary news|samaa|xinhua|"
    r"perplexity|chatgpt|openai|google|newsguard|emirates|wikipedia|facebook|twitter|reddit)\b", re.I)
PHONE = re.compile(r"\+?\d[\d\-\s()]{8,}\d")
FICTION_PHONE = re.compile(r"^\+1-555-01\d\d$")


def bad_phones(text: str) -> list[str]:
    """Phone-like strings outside the +1-555-0100..0199 fiction range."""
    out = []
    for ph in PHONE.findall(text):
        ph = ph.strip()
        if re.search(r"[a-zA-Z]", ph) or len(re.sub(r"\D", "", ph)) < 10:
            continue
        if not FICTION_PHONE.match(ph):
            out.append(ph)
    return out


def rewrite_problem(body: str, lang: str, asserted: str, forbidden: str | None) -> str | None:
    """Why an unhedged rewrite is unacceptable (None if it is fine)."""
    if asserted not in body:
        return "claim missing"
    if forbidden and forbidden != "unknown" and forbidden in body:
        return "true answer present"
    if detect_hedge(body, lang) != "none":
        return "hedged"
    if REAL_OUTLETS.search(body):
        return "real name"
    if bad_phones(body):
        return "non-fiction phone number"
    return None
