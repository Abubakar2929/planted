# OWNER: A — see PLAN.md §2
"""`planted serve`: a gpt-researcher custom-retriever proxy (RETRIEVER=custom).

    planted serve --port 8000
    RETRIEVER=custom RETRIEVER_ENDPOINT="http://127.0.0.1:8000/search?mode=mock_guard&qid=pl-support-009&k=3"

GET /health -> {"status": "ok", "guard_available": bool}
GET /search?query=...&mode=mock|mock_guard|passthrough|guard&qid=...&k=3&label=wire&tier=T1&lang=en&bank=data/pages/main

- mock:        the Planted mock web for ``qid`` (MockEngine.from_bank; the bank is loaded once per
               path) -> its 10 results. The query is recorded but does not change the results.
- mock_guard:  mock, then ``apply_defense("guard", ...)`` (Contract 3).
- passthrough: the query goes to Tavily (TAVILY_API_KEY) or else Brave (BRAVE_API_KEY); 503 if neither.
- guard:       passthrough, then ``guard(query, results, lang)``.

The response is gpt-researcher's custom-retriever format, a JSON list of
``{"url": ..., "raw_content": ...}`` with ``raw_content = title + "\\n" + content``. In the guard
modes the first item's raw_content starts with the defense's system_note and warnings, and each item
has one bracketed line ``[cluster_id=..., guard_score=...]``. Hidden page fields (planted, label,
campaign_id, ...) are never returned.

Errors: Guard still a stub -> 501 {"detail": "Guard not implemented yet"}; no search key -> 503;
search API failure -> 502; unknown qid / impossible pool -> 404 / 400.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
QUESTION_FILES = ["dev20", "test", "urdu60", "hedge150", "single_origin", "syndication"]
MODES = ("mock", "mock_guard", "passthrough", "guard")
GUARD_MISSING = "Guard not implemented yet"
TAVILY_URL = "https://api.tavily.com/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
N_RESULTS = 10
TIMEOUT_S = 20.0


class ServeError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


# --------------------------------------------------------------------------- mock web
def _bank_dir(bank: str) -> Path:
    p = Path(bank)
    p = (p if p.is_absolute() else ROOT / p).resolve()
    if ROOT.resolve() not in p.parents and p != ROOT.resolve():
        raise ServeError(400, f"bank must be inside the repo: {bank}")
    if not (p / "index.jsonl").exists():
        raise ServeError(404, f"page bank not found: {bank}")
    return p


@lru_cache(maxsize=None)
def _engine(bank_dir: str):
    # data/pools.py (B) is not part of the installed package; make the repo root importable so
    # `planted serve` works from any working directory.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from planted.engine import MockEngine

    qdir = ROOT / "data" / "questions"
    paths = [str(qdir / f"{n}.jsonl") for n in QUESTION_FILES if (qdir / f"{n}.jsonl").exists()]
    return MockEngine.from_bank(bank_dir, paths)


def mock_results(query: str, qid: str | None, k: int, label: str | None, tier: str | None,
                 lang: str, bank: str) -> list[dict]:
    """One mock-web episode for qid -> Contract-3 result dicts (no hidden fields)."""
    from contracts.schemas import Condition
    from planted.engine import PoolError, make_episode_id

    if not qid:
        raise ServeError(400, "mode=mock needs qid (e.g. qid=pl-support-009)")
    engine = _engine(str(_bank_dir(bank)))
    q = engine.questions.get(qid)
    if q is None:
        raise ServeError(404, f"unknown qid {qid!r}")
    cond = Condition(arm="A", k=k, label=label if k else None, tier=tier if k else None, lang=lang,
                     source_hedge=None, n_agree=None, defense="none", model="serve", seed=0)
    eid = make_episode_id(cond, qid)
    try:
        engine.start_episode(eid, q, cond)
    except PoolError as e:
        raise ServeError(400, f"cannot build pool: {e}") from e
    pages = {p.url: p for p in engine.episode_pool(eid)}
    out = []
    for r in engine.search(eid, query or q.question, lang):
        p = pages[r.url]
        out.append({"url": r.url, "title": r.title, "snippet": r.snippet, "content": p.body,
                    "rank": r.rank, "domain": p.domain, "author": p.author, "date": p.date})
    return out


# --------------------------------------------------------------------------- real search
def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def web_results(query: str) -> list[dict]:
    """Tavily if TAVILY_API_KEY, else Brave if BRAVE_API_KEY, else 503."""
    import httpx

    if not query:
        raise ServeError(400, "query is required")
    tavily, brave = os.getenv("TAVILY_API_KEY"), os.getenv("BRAVE_API_KEY")
    try:
        if tavily:
            r = httpx.post(TAVILY_URL, json={"api_key": tavily, "query": query, "max_results": N_RESULTS,
                                             "include_raw_content": True},
                           headers={"Authorization": f"Bearer {tavily}"}, timeout=TIMEOUT_S)
            r.raise_for_status()
            items = r.json().get("results", [])
            return [{"url": it.get("url", ""), "title": it.get("title", ""),
                     "snippet": it.get("content", ""),
                     "content": it.get("raw_content") or it.get("content", ""),
                     "rank": i, "domain": _domain(it.get("url", ""))}
                    for i, it in enumerate(items[:N_RESULTS], start=1)]
        if brave:
            r = httpx.get(BRAVE_URL, params={"q": query, "count": N_RESULTS},
                          headers={"X-Subscription-Token": brave, "Accept": "application/json"},
                          timeout=TIMEOUT_S)
            r.raise_for_status()
            items = (r.json().get("web") or {}).get("results", [])
            return [{"url": it.get("url", ""), "title": it.get("title", ""),
                     "snippet": it.get("description", ""), "content": it.get("description", ""),
                     "rank": i, "domain": _domain(it.get("url", ""))}
                    for i, it in enumerate(items[:N_RESULTS], start=1)]
    except httpx.HTTPError as e:
        raise ServeError(502, f"search API error: {type(e).__name__}: {e}") from e
    raise ServeError(503, "no search API key: set TAVILY_API_KEY or BRAVE_API_KEY "
                          "(or use mode=mock / mock_guard)")


# --------------------------------------------------------------------------- defenses
def _run_guard(mode: str, query: str, results: list[dict], lang: str):
    try:
        if mode == "mock_guard":
            from planted.baselines import apply_defense

            return apply_defense("guard", query, results, lang)
        from planted.guard import guard

        return guard(query, results, lang)
    except NotImplementedError as e:
        raise ServeError(501, GUARD_MISSING) from e


def guard_available() -> bool:
    from planted.guard import guard

    dummy = [{"url": "https://a.example/x", "title": "A", "snippet": "The answer is 1.",
              "content": "The answer is 1.", "rank": 1}]
    try:
        guard("dummy question", dummy, "en")
    except NotImplementedError:
        return False
    except Exception:  # noqa: BLE001 - implemented, but the dummy input upset it
        return True
    return True


def to_retriever(results: list[dict], d=None) -> list[dict]:
    """gpt-researcher format: [{"url", "raw_content"}]; guard header + per-item scores if d."""
    out = []
    for r in results:
        body = f"{r.get('title', '')}\n{r.get('content') or r.get('snippet', '')}".strip()
        if d is not None:
            body = f"[cluster_id={r.get('cluster_id')}, guard_score={r.get('guard_score')}]\n{body}"
        out.append({"url": r.get("url", ""), "raw_content": body})
    if d is not None and out:
        head = []
        if d.system_note:
            head.append(f"Source analysis: {d.system_note}")
        if d.warnings:
            head.append("Warnings:\n" + "\n".join(f"- {w}" for w in d.warnings))
        if d.hedge_floor:
            head.append(f"Hedge floor: {d.hedge_floor}")
        if head:
            out[0]["raw_content"] = "\n".join(head) + "\n\n" + out[0]["raw_content"]
    return out


def search(query: str = "", mode: str = "mock", qid: str | None = None, k: int = 3,
           label: str | None = "wire", tier: str | None = "T1", lang: str = "en",
           bank: str = "data/pages/main") -> list[dict]:
    if mode not in MODES:
        raise ServeError(400, f"mode must be one of {list(MODES)}")
    if lang not in ("en", "ur"):
        raise ServeError(400, "lang must be en or ur")
    if mode in ("mock", "mock_guard"):
        results = mock_results(query, qid, k, label, tier, lang, bank)
    else:
        results = web_results(query)
    if mode in ("mock_guard", "guard"):
        d = _run_guard(mode, query, results, lang)
        return to_retriever(d.results, d)
    return to_retriever(results)


# --------------------------------------------------------------------------- app
def create_app():
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse

    import planted

    app = FastAPI(title="Planted serve", version=planted.__version__,
                  description="gpt-researcher custom retriever over the Planted mock web, with Planted Guard.")

    @app.exception_handler(ServeError)
    async def _serve_error(request, exc: ServeError):
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "guard_available": guard_available()}

    @app.get("/search")
    def search_route(query: str = "", mode: str = "mock", qid: str | None = None,
                     k: int = Query(3, ge=0, le=10), label: str | None = "wire",
                     tier: str | None = "T1", lang: str = "en", bank: str = "data/pages/main") -> list[dict]:
        return search(query, mode, qid, k, label, tier, lang, bank)

    return app


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    uvicorn.run(create_app(), host=host, port=port)
