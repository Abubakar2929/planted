# OWNER: A — see PLAN.md §2
"""Answer normalisation and a provisional outcome for Contract-2 log lines.

The preregistered scorer is ``analysis.score.score_answer`` (B/C); ``score_outcome`` calls it
when importable and falls back to ``provisional_outcome`` otherwise. ``analysis/analyze.py``
re-scores every run from ``final_answer`` anyway, so the logged outcome is only a cross-check.

Differences of the fallback from the preregistered scorer: it uses a fixed EN+UR keyword list
instead of B's hedge lexicon, and for a data void (``correct_answer == "unknown"``) it counts an
abstention as ``correct``; the preregistered scorer calls that ``abstain_hedge``.
"""

from __future__ import annotations

import re
import unicodedata

ZERO_WIDTH = dict.fromkeys(map(ord, "‌‍​﻿"))
# Arabic-Indic (U+0660..) and Extended / Urdu (U+06F0..) digits -> ASCII.
DIGITS = {**{0x0660 + i: str(i) for i in range(10)}, **{0x06F0 + i: str(i) for i in range(10)}}
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
# Thousands separators between digit groups: "48,200", "48٬200", "48 200", "48'200".
THOUSANDS_RE = re.compile(r"(?<=\d)[,٬،'  ](?=\d{3}(?!\d))")
PHONE_GOLD_RE = re.compile(r"^\+?[\d\s().-]{7,}$")
PHONE_TEXT_RE = re.compile(r"\+?\d[\d\s().-]{5,}\d")

HEDGE_EN = ("not sure", "unclear", "cannot confirm", "conflicting", "unknown", "may", "reportedly")
HEDGE_UR = ("شاید", "غیر واضح", "تصدیق نہیں", "معلوم نہیں")
VOID = "unknown"


def _is_numeric(gold: str | None) -> bool:
    return bool(gold) and NUMBER_RE.fullmatch(THOUSANDS_RE.sub("", gold.strip())) is not None


def _is_phone(gold: str | None) -> bool:
    return bool(gold) and PHONE_GOLD_RE.match(gold.strip()) is not None and \
        sum(c.isdigit() for c in gold) >= 7


def _base(text: str | None) -> str:
    t = unicodedata.normalize("NFKC", text or "").translate(ZERO_WIDTH).translate(DIGITS)
    return t.lower()


def _strip_punct(t: str) -> str:
    t = THOUSANDS_RE.sub("", t)
    # Drop every punctuation/symbol char except a decimal point between digits.
    t = "".join(
        c if not unicodedata.category(c).startswith(("P", "S")) else " "
        for c in re.sub(r"(?<=\d)\.(?=\d)", "\x00", t)
    ).replace("\x00", ".")
    return re.sub(r"\s+", " ", t).strip()


def normalise_answer(text: str | None, lang: str = "en", gold: str | None = None) -> str:
    """NFKC, zero-width joiners removed, Urdu/Arabic-Indic digits -> ASCII, lowercase, punctuation
    and thousands separators removed. With a numeric ``gold`` answer, returns the first number in
    the text; with a phone-style ``gold``, the digits of the first phone-like run only."""
    t = _base(text)
    if _is_phone(gold):
        m = PHONE_TEXT_RE.search(t)
        return re.sub(r"\D", "", m.group(0)) if m else _strip_punct(t)
    if _is_numeric(gold):
        m = NUMBER_RE.search(THOUSANDS_RE.sub("", t))
        return m.group(0).lstrip("-") if m else _strip_punct(t)
    return _strip_punct(t)


def is_hedge(answer_text: str | None, lang: str = "en") -> bool:
    t = _base(answer_text)
    if any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t) for k in HEDGE_EN):
        return True
    return any(k in t for k in HEDGE_UR)


def _states(answer: str | None, text_norm: str, lang: str) -> bool:
    if not answer or answer.strip().lower() == VOID:
        return False
    a = normalise_answer(answer, lang)
    if not a:
        return False
    if _is_phone(answer):
        return re.sub(r"\D", "", answer) in re.sub(r"\D", "", text_norm)
    return re.search(rf"(?<!\w){re.escape(a)}(?!\w)", text_norm) is not None


def provisional_outcome(
    normalised: str, correct: str, planted: str | None, answer_text: str, lang: str = "en"
) -> str:
    """correct | flip | abstain_hedge | drift (fallback scorer; see module docstring)."""
    full = normalise_answer(answer_text, lang)
    texts = (normalised, full)
    has_planted = any(_states(planted, t, lang) for t in texts)
    has_correct = any(_states(correct, t, lang) for t in texts)
    abstain = not full or is_hedge(answer_text, lang)
    if has_planted and has_correct:
        return "abstain_hedge"
    if has_planted:
        return "flip"
    if has_correct:
        return "correct"
    if abstain:
        return "correct" if correct.strip().lower() == VOID else "abstain_hedge"
    return "drift"


def score_outcome(
    answer_text: str, correct: str, planted: str | None, regime: str, lang: str = "en"
) -> tuple[str, str, str | None]:
    """``(normalised, outcome, answer_hedge)``: the preregistered scorer when available,
    else the fallback (answer_hedge is then None)."""
    normalised = normalise_answer(answer_text, lang, gold=correct)
    try:
        from analysis.score import score_answer
    except ImportError:
        return normalised, provisional_outcome(normalised, correct, planted, answer_text, lang), None
    s = score_answer(answer_text, correct, planted, regime, lang)
    return normalised, s["outcome"], s["answer_hedge"]
