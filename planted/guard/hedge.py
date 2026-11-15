# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Hedge floor: the answer may never sound more certain than its sources (plan-v2.2 Step 9, PREREG P1)."""

from __future__ import annotations

from data.lexicons.lexicon import ORDER, detect_hedge

PREFIX = {
    "en": {
        "may": "This may not be confirmed: ",
        "preliminary": "According to preliminary reports, ",
        "disagree": "Sources disagree on this; ",
    },
    "ur": {
        "may": "ممکن ہے اس کی تصدیق نہ ہوئی ہو: ",
        "preliminary": "ابتدائی نتائج کے مطابق، ",
        "disagree": "ذرائع میں اس پر اختلاف ہے؛ ",
    },
}


def stronger(a: str | None, b: str | None) -> str | None:
    """The stronger of two hedge levels (None counts as no floor)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if ORDER.index(a) >= ORDER.index(b) else b


def hedge_floor(levels: list[str], gate_floor: str | None = None) -> str | None:
    """Strongest hedge among the pages supporting the top answer, or the gate's floor if stronger.
    Returns None when that is "none"."""
    floor = gate_floor
    for lv in levels:
        floor = stronger(floor, lv)
    return None if floor in (None, "none") else floor


def enforce(answer: str, hedge_floor: str | None, lang: str) -> str:
    """Prefix a fixed qualifier when the answer is less hedged than the floor. Deterministic and
    idempotent: an answer that already carries the floor (or any of our prefixes) is unchanged."""
    if hedge_floor in (None, "none"):
        return answer
    if hedge_floor not in ORDER:
        raise ValueError(f"unknown hedge level {hedge_floor!r}")
    lang = "ur" if lang == "ur" else "en"
    text = answer or ""
    if any(text.startswith(p) for table in PREFIX.values() for p in table.values()):
        return answer
    if ORDER.index(detect_hedge(text, lang)) >= ORDER.index(hedge_floor):
        return answer
    return PREFIX[lang][hedge_floor] + text
