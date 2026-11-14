# OWNER: B — see PLAN.md §2
"""Assemble the 10 search results for one episode from B's page banks (helper for A's engine).

    from data.pools import PageBank, build_pool
    bank = PageBank.load("data/pages/main")               # or data/heldout/pages for the Guard sweep
    pages = build_pool(bank, question, condition)         # -> list[Page], length 10, seeded order

Composition rules (k = condition.k planted pages; planted pages always come from ONE campaign:
condition.tier x condition.label, default label "neutral"):

    regime known          k planted + (10-k) honest pages (distinct outlets)
    regime void           k planted + (10-k) filler pages (entity pages that never state the fact)
    regime support        official site + k planted + (9-k) fillers
    regime single_origin  one true source + k planted + (9-k) fillers   (base qid = qid minus "-so")
    regime syndication    3 syndicated wire copies + 3 honest + 4 fillers; planted pages replace fillers
                          first, then honest pages                        (base qid = qid minus "-syn")
    regime hedge          condition.n_agree pages at condition.source_hedge + fillers

Urdu questions (qid ending "-ur") use the Urdu bank pages for the same fact. Order is a deterministic
shuffle keyed by (seed, qid, k, tier, label); A's engine may re-rank. Hidden fields (planted, label,
campaign_id, ...) stay on the Page objects for scoring; the engine must strip them before the agent.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from contracts.schemas import Condition, Page, Question

POOL_SIZE = 10


class PageBank:
    def __init__(self, pages: dict[str, Page], index: list[dict]):
        self.pages = pages
        self.by_role: dict[tuple, list[tuple[int, str]]] = defaultdict(list)
        self.by_role_any_label: dict[tuple, list[tuple[int, str]]] = defaultdict(list)
        for row in index:
            self.by_role[(row["qid"], row["role"], row["tier"], row["label"], row["hedge"])].append(
                (row["slot"], row["url"]))
            self.by_role_any_label[(row["qid"], row["role"], row["tier"], row["hedge"])].append(
                (row["slot"], row["url"]))
        for d in (self.by_role, self.by_role_any_label):
            for v in d.values():
                v.sort()
        self.index = index

    @classmethod
    def load(cls, folder: str | Path) -> PageBank:
        folder = Path(folder)
        pages = {}
        with open(folder / "pages.jsonl", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    p = Page.model_validate_json(line)
                    pages[p.url] = p
        index = [json.loads(l) for l in open(folder / "index.jsonl", encoding="utf-8") if l.strip()]
        return cls(pages, index)

    def get(self, qid: str, role: str, tier=None, label=None, hedge=None) -> list[Page]:
        if label is None:  # honest/filler/hedge pages mix labels: all labels for that role, by slot
            urls = self.by_role_any_label.get((qid, role, tier, hedge), [])
        else:
            urls = self.by_role.get((qid, role, tier, label, hedge), [])
        return [self.pages[u] for _, u in urls]

    def qids(self) -> set[str]:
        return {r["qid"] for r in self.index}


def base_qid(qid: str) -> str:
    """Page-bank key for a question: variants share the base fact's pages; Urdu keeps its suffix."""
    ur = qid.endswith("-ur")
    core = qid[:-3] if ur else qid
    for suf in ("-so", "-syn"):
        core = core.removesuffix(suf)
    return core + ("-ur" if ur else "")


def _take(pages: list[Page], n: int, what: str, qid: str) -> list[Page]:
    if n < 0 or n > len(pages):
        raise ValueError(f"pool for {qid}: need {n} {what} pages, bank has {len(pages)}")
    return pages[:n]


def build_pool(bank: PageBank, question: Question, condition: Condition) -> list[Page]:
    qid = base_qid(question.qid)
    k = condition.k
    if k < 0 or k > POOL_SIZE:
        raise ValueError(f"k={k} out of range")
    regime = question.regime
    label = condition.label or "neutral"
    planted: list[Page] = []
    if k:
        if not condition.tier:
            raise ValueError(f"{question.qid}: k={k} needs condition.tier")
        planted = _take(bank.get(qid, "planted", condition.tier, label), k, f"{condition.tier}/{label} planted", qid)

    fillers = bank.get(qid, "filler")
    if regime == "known":
        rest = _take(bank.get(qid, "honest"), POOL_SIZE - k, "honest", qid)
    elif regime == "void":
        rest = _take(fillers, POOL_SIZE - k, "filler", qid)
    elif regime in ("support", "single_origin"):
        true_src = bank.get(qid, "official") or bank.get(qid, "honest")[:1]
        if not true_src:
            raise ValueError(f"{question.qid}: no true source in bank")
        rest = true_src[:1] + _take(fillers, POOL_SIZE - 1 - k, "filler", qid)
    elif regime == "syndication":
        synd = _take(bank.get(qid, "syndicated"), 3, "syndicated", qid)
        honest = bank.get(qid, "honest") or bank.get(qid, "official")  # support: the official site only
        n_honest = min(3, len(honest))
        n_fill = POOL_SIZE - 3 - n_honest - k
        if n_fill < 0:  # planted pages replace fillers first, then honest pages
            n_honest += n_fill
            n_fill = 0
        rest = synd + _take(honest, n_honest, "honest", qid) + _take(fillers, n_fill, "filler", qid)
    elif regime == "hedge":
        n = condition.n_agree or 1
        level = condition.source_hedge or "none"
        rest = _take(bank.get(qid, "hedge", hedge=level), n, f"hedge/{level}", qid) + \
            _take(fillers, POOL_SIZE - n - k, "filler", qid)
    else:
        raise ValueError(f"unknown regime {regime}")

    pool = planted + rest
    if len(pool) != POOL_SIZE:
        raise AssertionError(f"{question.qid}: pool has {len(pool)} pages")
    rng = random.Random(f"{condition.seed}|{question.qid}|{k}|{condition.tier}|{label}|{condition.source_hedge}|{condition.n_agree}")
    rng.shuffle(pool)
    return pool


def load_questions(path: str | Path) -> list[Question]:
    return [Question.model_validate_json(l) for l in open(path, encoding="utf-8") if l.strip()]
