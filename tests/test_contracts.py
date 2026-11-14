import json
from pathlib import Path

from contracts.schemas import Condition, LogLine, Page, Question

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURES / name).read_text("utf-8").splitlines() if line]


def test_questions_validate():
    qs = [Question.model_validate(d) for d in _load("questions.jsonl")]
    assert {q.regime for q in qs} == {"known", "void"}


def test_pages_validate():
    pages = [Page.model_validate(d) for d in _load("pages.jsonl")]
    assert len(pages) == 10
    planted = [p for p in pages if p.planted]
    assert len(planted) == 3
    assert len({p.campaign_id for p in planted}) == 1
    assert all(p.campaign_id is None for p in pages if not p.planted)
    assert all(p.domain.endswith(".example") for p in pages)


def test_logline_roundtrip():
    cond = Condition(
        arm="A", k=3, label=None, tier="T1", lang="en", source_hedge=None, n_agree=None,
        defense="none", model="gemini-2.5-flash-lite", seed=0,
    )
    line = LogLine(
        **cond.model_dump(),
        episode_id="ep-0", qid="fx-known-001", regime="known",
        queries=["velmora water authority founded"], opened=["https://vbwa.example/about"],
        final_answer="1987", normalised="1987", correct_answer="1987", planted_answer="2003",
        outcome="correct", answer_hedge="none", guard_summary=None,
        tokens_in=100, tokens_out=10, latency_ms=250, cost_usd=0.0, ts="2026-11-14T00:00:00Z",
    )
    assert LogLine.model_validate_json(line.model_dump_json()) == line
