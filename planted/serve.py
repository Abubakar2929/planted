# OWNER: A — see PLAN.md §2
"""`planted serve --guard`: gpt-researcher custom-retriever proxy (RETRIEVER=custom)."""

from __future__ import annotations


def create_app(guard: bool = True):
    """TODO (A, PLAN.md §8): FastAPI app answering gpt-researcher with [{url, raw_content}],
    applying guard() to results when guard=True."""
    raise NotImplementedError


def serve(host: str = "127.0.0.1", port: int = 8000, guard: bool = True) -> None:
    """TODO (A, PLAN.md §8): run create_app() under uvicorn."""
    raise NotImplementedError
