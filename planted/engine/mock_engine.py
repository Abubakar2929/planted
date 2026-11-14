# OWNER: A — see PLAN.md §2
"""Deterministic, seeded mock search engine (Contract 1).

Page -> question convention (B: please follow this)
---------------------------------------------------
``contracts.schemas.Page`` has no ``qid`` field, so each page is tied to a question by:

1. an explicit ``"qid"`` key in the raw JSONL line, if present (pydantic drops it on
   validation, so the engine reads it from the raw dict first); otherwise
2. the first path segment of the url: ``https://<domain>/<qid>/<slug>``,
   e.g. ``https://northfen-wire.example/q017/vbwa-anniversary``.

Pages whose qid (from either rule) is not in the questions file are not indexed; their
urls are kept in ``MockEngine.unindexed`` so loaders can check nothing was lost.

Pool rules (``build_pool``), always exactly 10 pages
----------------------------------------------------
- planted: ``planted=True``, ``asserted_answer == question.planted_answer``, and matching
  ``cond.lang``, plus ``cond.label`` / ``cond.tier`` when those are set. ``cond.k`` of them.
- arm D (``cond.source_hedge`` set): ``cond.n_agree`` agree pages (``planted=False``,
  ``asserted_answer == question.correct_answer``, ``source_hedge == cond.source_hedge``),
  then filled with neutral pages (``planted=False``, ``label="neutral"``, not asserting
  the correct answer).
- other arms: filled with honest pages (``planted=False``).
- All pages must match ``cond.lang``. Answers compare after strip + casefold.
- Within each group, pages are taken in file order, so doses nest (k=1 ⊂ k=3 ⊂ k=5).
- Positions are then shuffled with ``random.Random(seed)``, where the seed is the SHA-256 of
  ``(cond.seed, qid, arm, k, label, tier)``. Python's ``hash()`` is salted per process, so
  it is not used. Same condition -> same order on every run.

Too few matching pages raises ``PoolError`` naming the group that is short.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from urllib.parse import urlparse

from contracts.schemas import Condition, Page, Question, SearchResult

POOL_SIZE = 10
NOT_FOUND = "Page not found"

# Short model names for episode ids; unknown models fall back to an alphanumeric slug.
MODEL_SHORT = {
    "gemini-2.5-flash-lite": "gflite",
}


class PoolError(ValueError):
    """Not enough pages to build a pool for a (question, condition)."""


def _norm(s: str | None) -> str:
    return (s or "").strip().casefold()


def _read_jsonl(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _qid_from_url(url: str) -> str | None:
    parts = [p for p in urlparse(url).path.split("/") if p]
    return parts[0] if len(parts) >= 2 else None


def _model_short(model: str) -> str:
    if model in MODEL_SHORT:
        return MODEL_SHORT[model]
    return re.sub(r"[^a-z0-9]", "", model.rsplit("/", 1)[-1].lower())


def make_episode_id(cond: Condition, qid: str) -> str:
    """Readable, unique id, e.g. ``A-k3-wire-T1-en-none-gflite-s0-q017``.

    Arm D adds the hedge level and agree count after lang: ``D-k0-na-na-en-hmay-a3-none-...``.
    """
    parts = [cond.arm, f"k{cond.k}", cond.label or "na", cond.tier or "na", cond.lang]
    if cond.source_hedge is not None:
        parts += [f"h{cond.source_hedge}", f"a{cond.n_agree}"]
    parts += [cond.defense, _model_short(cond.model), f"s{cond.seed}", qid]
    return "-".join(parts)


def _shuffle_seed(cond: Condition, qid: str) -> int:
    key = json.dumps([cond.seed, qid, cond.arm, cond.k, cond.label, cond.tier])
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


class MockEngine:
    """Serves B's pages per episode. Implements the search/open_url half of Contract 1."""

    def __init__(self, pages_path: str | list[str], questions_path: str) -> None:
        self.questions: dict[str, Question] = {
            q.qid: q for q in (Question.model_validate(d) for d in _read_jsonl(questions_path))
        }
        self.pages_by_qid: dict[str, list[Page]] = {qid: [] for qid in self.questions}
        self.unindexed: list[str] = []
        seen: set[str] = set()
        paths = [pages_path] if isinstance(pages_path, (str, Path)) else pages_path
        for path in paths:
            for raw in _read_jsonl(path):
                page = Page.model_validate(raw)
                if page.url in seen:
                    raise ValueError(f"duplicate page url {page.url!r} in {path}")
                seen.add(page.url)
                qid = raw.get("qid") or _qid_from_url(page.url)
                if qid in self.pages_by_qid:
                    self.pages_by_qid[qid].append(page)
                else:
                    self.unindexed.append(page.url)
        self._pools: dict[str, list[Page]] = {}
        self._traces: dict[str, dict[str, list[str]]] = {}

    make_episode_id = staticmethod(make_episode_id)

    def build_pool(self, question: Question, cond: Condition) -> list[Page]:
        qid = question.qid
        pages = [p for p in self.pages_by_qid.get(qid, []) if p.lang == cond.lang]
        where = f"qid={qid} lang={cond.lang}"

        def take(group: list[Page], n: int, what: str) -> list[Page]:
            if n < 0:
                raise PoolError(f"{where}: negative count {n} for {what}")
            if len(group) < n:
                raise PoolError(f"{where}: need {n} {what}, found {len(group)}")
            return group[:n]

        if cond.k > 0 and question.planted_answer is None:
            raise PoolError(f"{where}: k={cond.k} but question has no planted_answer")
        planted = take(
            [
                p for p in pages
                if p.planted
                and _norm(p.asserted_answer) == _norm(question.planted_answer)
                and (cond.label is None or p.label == cond.label)
                and (cond.tier is None or p.tier == cond.tier)
            ],
            cond.k,
            f"planted pages (label={cond.label}, tier={cond.tier})",
        )

        honest = [p for p in pages if not p.planted]
        if cond.source_hedge is not None:
            n_agree = cond.n_agree or 0
            agree = take(
                [
                    p for p in honest
                    if _norm(p.asserted_answer) == _norm(question.correct_answer)
                    and p.source_hedge == cond.source_hedge
                ],
                n_agree,
                f"agree pages (source_hedge={cond.source_hedge})",
            )
            neutral = take(
                [
                    p for p in honest
                    if p.label == "neutral"
                    and _norm(p.asserted_answer) != _norm(question.correct_answer)
                ],
                POOL_SIZE - cond.k - n_agree,
                "neutral filler pages",
            )
            pool = planted + agree + neutral
        else:
            pool = planted + take(honest, POOL_SIZE - cond.k, "honest pages")

        random.Random(_shuffle_seed(cond, qid)).shuffle(pool)
        return pool

    def start_episode(self, episode_id: str, question: Question, cond: Condition) -> None:
        """Build and store the pool; restarting an id replaces its pool and clears its trace."""
        self._pools[episode_id] = self.build_pool(question, cond)
        self._traces[episode_id] = {"queries": [], "opened": [], "not_found": []}

    def _pool(self, episode_id: str) -> list[Page]:
        if episode_id not in self._pools:
            raise KeyError(f"unknown episode {episode_id!r}; call start_episode first")
        return self._pools[episode_id]

    def search(self, episode_id: str, query: str, lang: str) -> list[SearchResult]:
        """Same 10 results for any query (the dose is fixed); the query is only recorded."""
        pool = self._pool(episode_id)
        self._traces[episode_id]["queries"].append(query)
        return [
            SearchResult(rank=i, url=p.url, title=p.title, snippet=p.snippet)
            for i, p in enumerate(pool, start=1)
        ]

    def open_url(self, episode_id: str, url: str) -> str:
        """Page body for urls in this episode's pool, else ``"Page not found"``."""
        for p in self._pool(episode_id):
            if p.url == url:
                self._traces[episode_id]["opened"].append(url)
                return p.body
        self._traces[episode_id]["not_found"].append(url)
        return NOT_FOUND

    def episode_pool(self, episode_id: str) -> list[Page]:
        """Full pages (hidden fields included) in rank order, for scoring and logging only."""
        return list(self._pool(episode_id))

    def episode_trace(self, episode_id: str) -> dict[str, list[str]]:
        """``{"queries": [...], "opened": [...], "not_found": [...]}`` for the logger."""
        self._pool(episode_id)
        return {k: list(v) for k, v in self._traces[episode_id].items()}
