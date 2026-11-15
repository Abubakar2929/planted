"""Inspect task with Inspect's mockllm model (no network)."""

from pathlib import Path

import pytest

pytest.importorskip("inspect_ai")

from inspect_ai import eval as inspect_eval  # noqa: E402
from inspect_ai.model import ModelOutput, get_model  # noqa: E402

from planted import inspect_task as it  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "data" / "pages" / "main" / "index.jsonl").exists(),
                                reason="no page bank")


def test_samples_load():
    task = it.planted_bench(k=3, split="dev")
    samples = list(task.dataset)
    assert len(samples) == 20
    md = samples[0].metadata
    for key in ("qid", "regime", "k", "label", "tier", "lang", "correct_answer", "planted_answer"):
        assert key in md
    assert md["k"] == 3 and md["label"] == "wire" and md["tier"] == "T1" and md["lang"] == "en"
    assert samples[0].target == md["correct_answer"]
    assert len(list(it.planted_bench(split="dev", limit=4).dataset)) == 4
    ur = list(it.planted_bench(split="test", lang="ur", limit=2).dataset)
    assert ur and all(s.metadata["lang"] == "ur" for s in ur)


def test_guard_stub_fails_cleanly(monkeypatch):
    import planted.baselines as b

    def stub(name, *a, **kw):
        raise NotImplementedError(f"defense {name!r} not implemented yet")

    monkeypatch.setattr(b, "apply_defense", stub)
    with pytest.raises(it.PrerequisiteError, match="Guard not implemented yet"):
        it.planted_bench(guard=True)


def _scripted(planted_or_correct: str):
    """search -> open first result -> submit(answer)."""
    state = {"i": 0}

    def outputs(messages, tools, tool_choice, config):
        state["i"] += 1
        names = {t.name for t in tools}
        assert {"search", "open", "submit"} <= names  # tools registered
        if state["i"] == 1:
            return ModelOutput.for_tool_call("mockllm/model", "search", {"query": "q"})
        if state["i"] == 2:
            url = next(l for l in messages[-1].text.splitlines() if l.startswith("URL: "))[5:]
            return ModelOutput.for_tool_call("mockllm/model", "open", {"url": url})
        return ModelOutput.for_tool_call("mockllm/model", "submit", {"answer": planted_or_correct})
    return outputs


@pytest.mark.parametrize("which,want", [("planted_answer", "flip"), ("correct_answer", "correct")])
def test_eval_with_mockllm_scores(tmp_path, which, want):
    task = it.planted_bench(k=3, split="dev", limit=1)
    md = list(task.dataset)[0].metadata
    model = get_model("mockllm/model", custom_outputs=_scripted(md[which]))
    (log,) = inspect_eval(task, model=model, log_dir=str(tmp_path), display="none")
    assert log.status == "success", log.error
    (sample,) = log.samples
    score = next(iter(sample.scores.values()))
    assert score.value in it.OUTCOMES
    assert score.value == want
    assert score.metadata["searches"] == 1
    tool_msgs = [m for m in sample.messages if m.role == "tool"]
    assert any("URL: https://" in m.text for m in tool_msgs)  # search results
    assert any(len(m.text) <= it.OPEN_CHARS for m in tool_msgs)
    metrics = log.results.scores[0].metrics
    assert {"flip_rate", "accuracy"} <= set(metrics)
    assert metrics["flip_rate"].value == (1.0 if want == "flip" else 0.0)


def test_search_cap():
    assert it.MAX_SEARCHES == 3 and it.MESSAGE_LIMIT == 8 and it.OPEN_CHARS == 2000
