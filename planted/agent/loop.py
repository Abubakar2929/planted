# OWNER: A — see PLAN.md §2
"""Agent tool loop (search / open_url) over LiteLLM."""

from __future__ import annotations

from contracts.schemas import Condition, LogLine, Question, SearchEngine


def run_episode(
    question: Question, condition: Condition, engine: SearchEngine, episode_id: str
) -> LogLine:
    """TODO (A, PLAN.md §8): run one agent episode and return one Contract-2 LogLine.

    - Tool loop on Gemini 2.5 Flash-Lite and GPT-OSS-120B (Groq) via LiteLLM.
    - Every model call goes through planted.agent.cache with condition.seed.
    - Defenses are called only through Contract 3 (planted.baselines.apply_defense).
    - A rerun with the same inputs must be byte-identical.
    """
    raise NotImplementedError
