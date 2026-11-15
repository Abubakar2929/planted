# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Text normalisation for Guard (plan-v2.2 Step 4)."""

from __future__ import annotations

import re
import unicodedata

_FOLD = str.maketrans({
    "ي": "ی", "ى": "ی",
    "ك": "ک",
    "ه": "ہ", "ۀ": "ہ", "ۃ": "ہ", "ة": "ہ",
    **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic digits
    **{chr(0x06F0 + i): str(i) for i in range(10)},  # Extended Arabic-Indic (Urdu) digits
    "٬": ",", "٫": ".",
})
# Arabic harakat, superscript alef, Quranic marks, tatweel
_DIACRITICS = re.compile(r"[ً-ٰٟۖ-ۭـ]")
_ZW = re.compile(r"[​-‏⁠﻿]")
SHINGLE_N = 5


def normalise_text(text: str, lang: str = "en") -> str:
    """NFKC; ZWNJ/ZWJ and Arabic diacritics stripped; Urdu/Arabic letter variants folded
    (ی/ي/ى -> ی, ک/ك -> ک, ہ/ه/ۃ/ة -> ہ); Urdu/Arabic-Indic digits -> ASCII; lower case;
    whitespace collapsed. Applied to every language (EN pages may quote Urdu and vice versa)."""
    t = unicodedata.normalize("NFKC", text or "")
    t = _ZW.sub("", t)
    t = _DIACRITICS.sub("", t.translate(_FOLD))
    t = t.replace("’", "'").lower()
    return re.sub(r"\s+", " ", t).strip()


normalize = normalise_text  # old stub name


def shingles(text: str, lang: str = "en", n: int = SHINGLE_N) -> set[str]:
    """Word n-grams for English, character n-grams for Urdu (word segmentation is unreliable)."""
    t = normalise_text(text, lang)
    if lang == "ur":
        t = re.sub(r"[^\w]+", " ", t).strip()
        if len(t) <= n:
            return {t} if t else set()
        return {t[i: i + n] for i in range(len(t) - n + 1)}
    words = re.findall(r"\w+", t)
    if len(words) <= n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i: i + n]) for i in range(len(words) - n + 1)}
