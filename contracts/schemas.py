# OWNER: SHARED — see PLAN.md §2 (changes need an [ALL] commit)
"""CONTRACTS v1 DRAFT — team must review together before tag contracts-v1. Changes need [ALL] commit.

Implements PLAN.md §4:
- Contract 1 (data and engine): Page, Question, Condition, SearchResult, SearchEngine.
- Contract 2 (one log line per agent run): LogLine.
- Contract 3 (defense interface): DefenseOut, GuardResult, Defense.

Scaffold decisions to confirm at review (not specified in PLAN.md §4):
- SearchResult.rank is 1-based.
- LogLine field types (queries/opened as list[str], latency_ms as int, ts as ISO-8601 str,
  guard_summary as free text).
- GuardResult has the same fields as DefenseOut (PLAN.md: guard() == apply_defense("guard", ...)).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

Lang = Literal["en", "ur"]

# ---------------------------------------------------------------------------
# Contract 1: data and engine
# ---------------------------------------------------------------------------


class Page(BaseModel):
    url: str
    domain: str
    title: str
    snippet: str
    body: str
    lang: Lang
    author: str | None
    date: str | None
    # hidden from the agent: scoring only
    planted: bool
    campaign_id: str | None
    label: Literal["wire", "propaganda", "blog", "official", "neutral"]
    tier: Literal["T0", "T1", "T2", "T3", "T4"] | None
    asserted_answer: str
    source_hedge: Literal["none", "may", "preliminary", "disagree"] | None


class Question(BaseModel):
    qid: str
    lang: Lang
    split: Literal["dev", "test"]
    regime: Literal["known", "void", "support", "single_origin", "syndication", "hedge"]
    question: str
    correct_answer: str
    planted_answer: str | None


class Condition(BaseModel):
    arm: Literal["A", "B", "D", "E", "G", "T4", "RW"]
    k: int
    label: str | None
    tier: str | None
    lang: str
    source_hedge: str | None
    n_agree: int | None
    defense: Literal["none", "prompt", "pagevote", "guard", "guard_noprov"]
    model: str
    seed: int


class SearchResult(BaseModel):
    """What the agent sees from search(): rank, url, title, snippet only."""

    rank: int
    url: str
    title: str
    snippet: str


@runtime_checkable
class SearchEngine(Protocol):
    """Engine API (A implements; B supplies the pages)."""

    def search(self, episode_id: str, query: str, lang: str) -> list[SearchResult]: ...

    def open_url(self, url: str) -> str: ...


# ---------------------------------------------------------------------------
# Contract 2: one log line per agent run (logs/*.jsonl)
# ---------------------------------------------------------------------------


class LogLine(Condition):
    """Every field of Condition, plus the per-run fields below."""

    episode_id: str
    qid: str
    regime: str
    queries: list[str]
    opened: list[str]
    final_answer: str
    normalised: str
    correct_answer: str
    planted_answer: str | None
    outcome: Literal["correct", "flip", "abstain_hedge", "drift"]
    answer_hedge: str | None
    guard_summary: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    ts: str


# ---------------------------------------------------------------------------
# Contract 3: defense interface (C implements; A's agent loop calls it)
# ---------------------------------------------------------------------------

DefenseName = Literal["none", "prompt", "pagevote", "guard", "guard_noprov"]


class DefenseOut(BaseModel):
    # Reordered results; each may add cluster_id, guard_score, note.
    # Result dict keys: url, title, snippet, content, rank (+ optional domain, author, date).
    results: list[dict]
    # e.g. "Answer X: 6 pages / 1 origin; Answer Y: 3 pages / 3 origins"
    system_note: str | None
    # e.g. "DATA_VOID: <2 independent origins"
    warnings: list[str]
    # min hedge the final answer must carry
    hedge_floor: str | None


class GuardResult(DefenseOut):
    """Return type of the public guard() API; equals apply_defense("guard", ...)."""


@runtime_checkable
class Defense(Protocol):
    def apply_defense(
        self, name: str, query: str, results: list[dict], lang: str
    ) -> DefenseOut: ...

    def enforce(self, answer: str, hedge_floor: str | None, lang: str) -> str: ...
