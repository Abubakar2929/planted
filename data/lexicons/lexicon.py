# OWNER: B — see PLAN.md §2
"""Hedge lexicon helpers (EN + UR, 4 levels), shared by scoring and the hedge floor.

    from data.lexicons.lexicon import detect_hedge, qualify, normalise
    detect_hedge("The figure may be 40%.", "en")         -> "may"
    qualify("40%", "preliminary", "en")                   -> "According to preliminary, unconfirmed reports, 40%."

This module only reads the JSON lexicons in this folder; it contains no generator logic.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["none", "may", "preliminary", "disagree"]
_FOLD = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ه": "ہ", "ۀ": "ہ", "ة": "ہ"})
_DIACRITICS = re.compile(r"[ً-ْٰۖ-ۭ]")


@cache
def load(lang: str) -> dict:
    return json.loads((HERE / f"hedge_{lang}.json").read_text(encoding="utf-8"))


def normalise(text: str, lang: str = "en") -> str:
    t = unicodedata.normalize("NFKC", text).replace("‌", "").replace("‍", "")
    if lang == "ur":
        t = _DIACRITICS.sub("", t.translate(_FOLD))
    t = t.replace("’", "'").lower()
    return re.sub(r"\s+", " ", t).strip()


def _matches(marker: str, text: str, lang: str) -> bool:
    m = normalise(marker, lang)
    if lang == "ur":
        return m in text
    return re.search(r"(?<![a-z])" + re.escape(m) + r"(?![a-z])", text) is not None


def detect_hedge(text: str, lang: str = "en") -> str:
    """Highest hedge level whose markers appear in the text (none if no marker matches)."""
    lex = load(lang)
    t = normalise(text, lang)
    if lang == "en":  # "May" the month is not a hedge: mask dates such as "14 may 1998" / "may 1998"
        t = re.sub(r"\b\d{1,2} may\b|\bmay \d{1,2}(st|nd|rd|th)?\b|\bmay \d{4}\b|\bmay,? \d{4}\b", " <month> ", t)
    best = "none"
    for level in ORDER[1:]:
        if any(_matches(mk, t, lang) for mk in lex["levels"][level]["markers"]):
            best = level
    return best


def coarse(level: str, lang: str = "en") -> str:
    return load(lang)["coarse"][level]


def is_abstention(text: str, lang: str = "en") -> bool:
    t = normalise(text, lang)
    return any(_matches(mk, t, lang) for mk in load(lang)["abstain_markers"])


def qualify(answer: str, level: str | None, lang: str = "en") -> str:
    """Templated qualifier carrying at least the given hedge level (no LLM call)."""
    if not level or level == "none":
        return answer
    return load(lang)["levels"][level]["qualifier"].replace("{answer}", answer)


def at_least(a: str, b: str) -> bool:
    """True if hedge level a is at least as strong as b."""
    return ORDER.index(a) >= ORDER.index(b)
