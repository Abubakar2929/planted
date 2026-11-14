# OWNER: B — see PLAN.md §2
"""Text similarity used by the T4 adaptive attacker to pick the least-similar candidate.

The plan's T4 attacker optimises against "Guard's own embedder". The model name is public in the plan
(paraphrase-multilingual-MiniLM-L12-v2); nothing here reads Guard code. If sentence-transformers and
that model are available locally it is used; otherwise a deterministic character 5-gram TF-IDF cosine
is used. Which one ran is reported by `backend_name()` and recorded in the page manifest.
"""

from __future__ import annotations

import math
import os
import re
import unicodedata
from collections import Counter

ST_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_model = None
_backend = None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("‌", "").replace("‍", "")
    return re.sub(r"\s+", " ", text)


def _char_ngrams(text: str, n: int = 5) -> Counter:
    t = _norm(text)
    return Counter(t[i:i + n] for i in range(max(0, len(t) - n + 1)))


def _load_st():
    global _model, _backend
    if _backend is not None:
        return _model
    if os.environ.get("PLANTED_EMBEDDER", "auto") == "tfidf":
        _backend = "char5-tfidf"
        return None
    try:
        from sentence_transformers import SentenceTransformer  # optional dependency

        _model = SentenceTransformer(ST_MODEL)
        _backend = ST_MODEL
    except Exception:  # not installed, or model not cached offline
        _model, _backend = None, "char5-tfidf"
    return _model


def backend_name() -> str:
    _load_st()
    return _backend or "char5-tfidf"


def _tfidf_vectors(texts: list[str]) -> list[dict]:
    grams = [_char_ngrams(t) for t in texts]
    df = Counter(g for c in grams for g in c)
    n = len(texts)
    vecs = []
    for c in grams:
        v = {g: tf * math.log((1 + n) / (1 + df[g]) + 1) for g, tf in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({g: x / norm for g, x in v.items()})
    return vecs


def _dot(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def similarity_matrix(texts: list[str]) -> list[list[float]]:
    """Pairwise cosine similarity for a small set of texts (a campaign plus candidates)."""
    model = _load_st()
    if model is not None:
        emb = model.encode(texts, normalize_embeddings=True)
        return [[float(sum(x * y for x, y in zip(a, b))) for b in emb] for a in emb]
    vecs = _tfidf_vectors(texts)
    return [[_dot(a, b) for b in vecs] for a in vecs]


def pick_least_similar(selected: list[str], candidates: list[str]) -> int:
    """Index of the candidate whose maximum similarity to the already-selected texts is lowest."""
    if not selected:
        return 0
    texts = selected + candidates
    sim = similarity_matrix(texts)
    k = len(selected)
    scores = [max(sim[k + i][j] for j in range(k)) for i in range(len(candidates))]
    return min(range(len(candidates)), key=lambda i: (scores[i], i))
