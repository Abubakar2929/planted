# OWNER: A — see PLAN.md §2
"""Inspect task: `inspect eval planted/inspect_task.py -T guard=true -T tier=T1`."""

from __future__ import annotations


def planted_task(guard: bool = False, tier: str = "T1"):
    """TODO (A, PLAN.md §8): build an inspect_ai Task over the Planted questions.

    Import inspect_ai inside this function (or decorate with @task once implemented)
    so importing this module stays cheap.
    """
    raise NotImplementedError
