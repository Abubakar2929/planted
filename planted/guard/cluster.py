# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""Origin clustering (plan-v2.2 Steps 3-5): a page graph over one result list, origins = connected
components (union-find). Every edge records which signal(s) created it.

Edges
-----
content     MinHash (datasketch, NUM_PERM perms, seeded) Jaccard >= tau_content on answer-masked,
            normalised text: word 5-grams (EN), character 5-grams (UR).
provenance  (strong signals, each is an edge on its own)
            domain_family   same registrable-label stem after stripping news-ish affixes and digits
            boilerplate     same first or last non-empty line that names something (a capitalised word
                            after the first, or a digit), or a shared byline ("By <name>", ...)
            author_date     same author AND same date
            cited_origin    same "originally published ..." / "source: ..." reference
embedding   cosine >= tau_embed on answer-masked text (multilingual MiniLM, CPU, lazy, cached by text
            hash), added only for a pair that also has a weak provenance signal (same author, same
            date, or a shared non-trivial line), since a strong signal is already an edge by itself.

Only the visible result keys (url, domain, title, snippet, content, author, date) are read.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from planted.guard.normalize import normalise_text, shingles

_URDU = re.compile(r"[؀-ۿ]")

# Generic news/outlet words stripped from a domain label to find its family stem
# ("pelrodale-news", "pelrodaledaily", "pelrodale24" -> "pelrodale").
DOMAIN_AFFIXES = sorted("""
news daily the online times post wire today now info press agency bureau service services gazette herald
journal report reports chronicle record observer echo courier tribune review weekly live network media hub
notebook notes blog official truth patriot voice insider watch headlines headline update updates digest
express evening morning star standard mail bulletin dispatch monitor sentinel globe register real my
local world central national community radio tv channel feed newswire wires paper
""".split(), key=len, reverse=True)
MIN_STEM = 4
MIN_LINE = 12        # boilerplate lines shorter than this are ignored ("Advertisement")
MIN_WEAK_LINE = 20   # shared lines used as a weak signal

_BYLINE = re.compile(r"^(?:by|reporting by|filed by|posted by|written by|story by|از|رپورٹ)\b", re.I)
_CITED = re.compile(
    r"(?:originally (?:published|appeared|reported)\s+(?:in|on|at|by)\s+|\bsource\s*:\s*)"
    r"([^\n.;,]{3,80})", re.I)
_URL = re.compile(r"https?://[^\s)\]>\"']+")

STRONG = ("domain_family", "boilerplate", "author_date", "cited_origin")


@dataclass
class Graph:
    cluster_ids: list[int]
    edges: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# page features
# ---------------------------------------------------------------------------

def page_lang(text: str, default: str = "en") -> str:
    letters = re.findall(r"[^\W\d_]", text or "")
    if not letters:
        return default
    ur = sum(bool(_URDU.match(c)) for c in letters)
    return "ur" if ur / len(letters) > 0.3 else "en"


def domain_of(r: dict) -> str:
    d = (r.get("domain") or urlparse(r.get("url") or "").hostname or "").lower()
    return d[4:] if d.startswith("www.") else d


def domain_stem(domain: str) -> str | None:
    """Registrable label minus digits, hyphens and generic news affixes; None if too short."""
    labels = [x for x in domain.lower().split(".") if x]
    if not labels:
        return None
    label = labels[-2] if len(labels) >= 2 else labels[0]
    parts = [p for p in re.split(r"[-_\d]+", label) if p]
    parts = [p for p in parts if p not in DOMAIN_AFFIXES]
    if not parts:  # only generic words ("news.example"): no family signal
        return None
    s = "".join(parts)
    changed = True
    while changed:
        changed = False
        for w in DOMAIN_AFFIXES:
            if s.endswith(w) and len(s) - len(w) >= MIN_STEM:
                s, changed = s[: -len(w)], True
                break
            if s.startswith(w) and len(s) - len(w) >= MIN_STEM:
                s, changed = s[len(w):], True
                break
    return s if len(s) >= MIN_STEM else None


def _lines(r: dict) -> list[str]:
    return [normalise_text(x) for x in (r.get("content") or "").split("\n") if x.strip()]


def distinctive(line: str) -> bool:
    """A chrome line names something (a capitalised word after the first, or a digit), so two outlets
    sharing it are plausibly one outlet. Generic genre lines ("Thanks for reading!") are not provenance."""
    words = line.split()
    named = any(w[:1].isupper() and not words[k][-1:] in ".!?:;" for k, w in enumerate(words[1:]))
    return named or any(c.isdigit() for c in line)


def boilerplate_keys(r: dict) -> set[str]:
    raw = [x.strip() for x in (r.get("content") or "").split("\n") if x.strip()]
    keys = set()
    for tag, ln in (("first", raw[:1]), ("last", raw[-1:])):
        if ln and len(ln[0]) >= MIN_LINE and distinctive(ln[0]):
            keys.add(f"{tag}:" + normalise_text(ln[0]))
    for ln in raw:
        norm = normalise_text(ln)
        if _BYLINE.match(norm) and len(norm) >= MIN_LINE:
            keys.add("by:" + norm)
    return keys


def cited_origins(r: dict) -> set[str]:
    body = r.get("content") or ""
    out = {normalise_text(m[1]) for m in _CITED.finditer(body)}
    for m in _CITED.finditer(body):
        out |= {u.rstrip(".,").lower() for u in _URL.findall(m[0] + body[m.end(): m.end() + 120])}
    return {x for x in out if len(x) >= 3}


def mask_answers(text: str, answers: list[str]) -> str:
    """Normalised text with every extracted answer string replaced by a placeholder."""
    t = normalise_text(text)
    for a in sorted({normalise_text(a) for a in answers if a}, key=len, reverse=True):
        if len(a) >= 2:
            t = t.replace(a, " ansmask ")
    return re.sub(r"\s+", " ", t).strip()


# ---------------------------------------------------------------------------
# embeddings (lazy, cached, mockable)
# ---------------------------------------------------------------------------

_embedder = None          # callable(list[str]) -> list[list[float]] (unit vectors)
_embed_error: str | None = None
_embed_cache: dict[str, list[float]] = {}


def set_embedder(fn) -> None:
    """Install an embedder (tests mock it); None resets to the lazy default."""
    global _embedder, _embed_error
    _embedder, _embed_error = fn, None
    _embed_cache.clear()


def _default_embedder():
    from sentence_transformers import SentenceTransformer

    from planted.guard import config

    model = SentenceTransformer(config.EMBED_MODEL, device="cpu")

    def embed(texts: list[str]):
        return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True,
                            show_progress_bar=False).tolist()

    return embed


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Unit vectors for texts (cached by sha256), or None if the model cannot load."""
    global _embedder, _embed_error
    if _embed_error is not None:
        return None
    if _embedder is None:
        try:
            _embedder = _default_embedder()
        except Exception as e:  # noqa: BLE001 - missing package, no network, bad weights...
            _embed_error = f"{type(e).__name__}: {e}"[:200]
            return None
    keys = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    todo = [(k, t) for k, t in zip(keys, texts) if k not in _embed_cache]
    if todo:
        try:
            vecs = _embedder([t for _, t in todo])
        except Exception as e:  # noqa: BLE001
            _embed_error = f"{type(e).__name__}: {e}"[:200]
            return None
        for (k, _), v in zip(todo, vecs):
            _embed_cache[k] = list(v)
    return [_embed_cache[k] for k in keys]


def embed_error() -> str | None:
    return _embed_error


def _cos(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------

class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def _minhashes(sh: list[set[str]], num_perm: int, seed: int):
    from datasketch import MinHash

    out = []
    for s in sh:
        m = MinHash(num_perm=num_perm, seed=seed)
        for x in sorted(s):
            m.update(x.encode("utf-8"))
        out.append(m)
    return out


@dataclass
class PairFeatures:
    """Threshold-independent pair evidence for one result list (computed once, thresholded cheaply)."""
    n: int
    jaccard: dict[tuple[int, int], float]            # MinHash Jaccard, pairs with shingles on both sides
    strong: dict[tuple[int, int], list[str]]         # provenance signals that are edges by themselves
    cosine: dict[tuple[int, int], float]             # embedding cosine for weak-signal pairs only
    warnings: list[str] = field(default_factory=list)


def pair_features(results: list[dict], answers: list[str | None], lang: str = "en", *,
                  use_provenance: bool = True, use_embeddings: bool = True,
                  num_perm: int = 128, seed: int = 1) -> PairFeatures:
    n = len(results)
    pool_answers = [a for a in answers if a]
    texts = [(r.get("content") or r.get("snippet") or "") for r in results]
    masked = [mask_answers(t, pool_answers) for t in texts]
    langs = [page_lang(t, lang) for t in texts]
    sh = [shingles(m, lg) for m, lg in zip(masked, langs)]
    mh = _minhashes(sh, num_perm, seed)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    jac = {(i, j): mh[i].jaccard(mh[j]) for i, j in pairs if sh[i] and sh[j]}

    strong: dict[tuple[int, int], list[str]] = {}
    cosine: dict[tuple[int, int], float] = {}
    warnings: list[str] = []
    if use_provenance:
        stems = [domain_stem(domain_of(r)) for r in results]
        boiler = [boilerplate_keys(r) for r in results]
        cited = [cited_origins(r) for r in results]
        authors = [normalise_text(r.get("author") or "") for r in results]
        dates = [normalise_text(str(r.get("date") or "")) for r in results]
        line_sets = [{x for x in _lines(r) if len(x) >= MIN_WEAK_LINE} for r in results]
        weak_pairs = []
        for i, j in pairs:
            sig = []
            if stems[i] and stems[i] == stems[j]:
                sig.append("domain_family")
            if boiler[i] & boiler[j]:
                sig.append("boilerplate")
            if authors[i] and dates[i] and authors[i] == authors[j] and dates[i] == dates[j]:
                sig.append("author_date")
            if cited[i] & cited[j]:
                sig.append("cited_origin")
            if sig:
                strong[(i, j)] = sig
            elif (authors[i] and authors[i] == authors[j]) or (dates[i] and dates[i] == dates[j]) \
                    or line_sets[i] & line_sets[j]:
                weak_pairs.append((i, j))
        if use_embeddings and weak_pairs:
            idx = sorted({x for p in weak_pairs for x in p})
            vecs = embed_texts([masked[x] for x in idx])
            if vecs is None:
                warnings.append(f"EMBEDDINGS_UNAVAILABLE: embedding edges skipped ({embed_error()})")
            else:
                v = dict(zip(idx, vecs))
                cosine = {(i, j): _cos(v[i], v[j]) for i, j in weak_pairs}
    return PairFeatures(n=n, jaccard=jac, strong=strong, cosine=cosine, warnings=warnings)


def graph_from(f: PairFeatures, *, tau_content: float, tau_embed: float,
               use_provenance: bool = True) -> Graph:
    """Edges at the given thresholds -> connected components (union-find)."""
    signals: dict[tuple[int, int], dict] = {}

    def add(key: tuple[int, int], sig: str, **extra) -> None:
        e = signals.setdefault(key, {"i": key[0], "j": key[1], "signals": []})
        e["signals"].append(sig)
        e.update(extra)

    for key, jac in f.jaccard.items():
        if jac >= tau_content:
            add(key, "content", jaccard=round(jac, 3))
    if use_provenance:
        for key, sigs in f.strong.items():
            for s in sigs:
                add(key, s)
        for key, c in f.cosine.items():
            if c >= tau_embed:
                add(key, "embedding", cosine=round(c, 3))
    uf = _UF(f.n)
    for i, j in signals:
        uf.union(i, j)
    roots: dict[int, int] = {}
    cluster_ids = [roots.setdefault(uf.find(i), len(roots)) for i in range(f.n)]
    return Graph(cluster_ids=cluster_ids, edges=[signals[k] for k in sorted(signals)],
                 warnings=list(f.warnings) if use_provenance else [])


def build_graph(results: list[dict], answers: list[str | None], lang: str = "en", *,
                use_provenance: bool = True, use_embeddings: bool = True,
                tau_content: float = 0.6, tau_embed: float = 0.92,
                num_perm: int = 128, seed: int = 1) -> Graph:
    """Page graph -> origins. ``answers`` are the per-page extracted answers (masked out of the text)."""
    f = pair_features(results, answers, lang, use_provenance=use_provenance,
                      use_embeddings=use_embeddings, num_perm=num_perm, seed=seed)
    return graph_from(f, tau_content=tau_content, tau_embed=tau_embed, use_provenance=use_provenance)


def cluster_origins(results: list[dict], lang: str, answers: list[str | None] | None = None,
                    **kw) -> list[int]:
    """One cluster_id per result (connected components)."""
    return build_graph(results, answers or [None] * len(results), lang, **kw).cluster_ids
