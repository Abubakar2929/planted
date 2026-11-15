# OWNER: A — see PLAN.md §2
"""Threaded, resumable, budget-capped sweep runner.

    stats = run_sweep(runs, "logs/pilot_A.jsonl", workers=8, max_usd=5)

- **Threads:** ``workers`` threads; the provider semaphores in ``planted.providers`` still cap
  in-flight requests per provider (Gemini 8, Groq 4), so extra workers just wait.
- **Resume:** episode ids already in the output file are skipped; new lines are appended, never
  overwritten (``JsonlLogger`` appends one flushed line per run).
- **Errors:** an exception in one run is logged to ``errors_path`` (default logs/errors.jsonl) as
  one JSON line (ts, episode_id, grid, error, traceback tail) and the sweep goes on.
- **Budget:** ``max_usd`` is checked against real spend (``cache.spent_usd``, cache misses only)
  before every submission. Once reached, nothing new starts; the runs already in flight (at most
  ``workers``) finish and are logged, so spend can pass the cap by at most ``workers`` runs.
- **Progress:** a tqdm bar, and a spend line every ``report_every`` finished episodes.
"""

from __future__ import annotations

import json
import threading
import traceback
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tqdm import tqdm


def done_ids(path: str | Path) -> tuple[set[str], int]:
    """Episode ids already logged in ``path`` and the number of unreadable lines."""
    ids, bad = set(), 0
    p = Path(path)
    if not p.exists():
        return ids, bad
    for line in open(p, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            ids.add(json.loads(line)["episode_id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            bad += 1
    return ids, bad


def plan_runs(runs: list, engines: dict | None = None) -> tuple[list, Counter, dict]:
    """Drop runs whose pool cannot be built (counted per reason) and duplicate episode ids.

    Returns (valid runs, Counter of skip reasons, {bank: MockEngine})."""
    from planted.engine import MockEngine, PoolError

    engines = {} if engines is None else engines
    valid, skipped, seen = [], Counter(), set()
    for r in runs:
        if r.episode_id in seen:
            skipped["duplicate episode_id"] += 1
            continue
        seen.add(r.episode_id)
        eng = engines.get(r.bank)
        if eng is None:
            eng = engines[r.bank] = MockEngine.from_bank(r.bank, [])
        try:
            eng.build_pool(r.question, r.cond)
        except PoolError as e:
            skipped[f"{r.grid} {r.question.qid} k={r.cond.k} {r.cond.tier}/{r.cond.label}: {e}"] += 1
            continue
        valid.append(r)
    return valid, skipped, engines


def _default_run_fn(engines: dict) -> Callable:
    from planted.agent.single_call import run_single

    def fn(run, logger, cache):
        return run_single(engines[run.bank], run.question, run.cond, logger, cache=cache,
                          prompt_style=run.style, tag=run.tag)
    return fn


def run_sweep(runs: list, out: str | Path, *, workers: int = 8, max_usd: float | None = None,
              cache=None, run_fn: Callable | None = None, engines: dict | None = None,
              errors_path: str | Path = "logs/errors.jsonl", report_every: int = 100,
              progress: bool = True) -> dict:
    """Run every not-yet-logged run. ``run_fn(run, logger, cache) -> LogLine`` (default: run_single
    on the run's bank engine). ``cache`` needs ``spent_usd``, ``hits`` and ``misses``."""
    from planted.agent.logger import JsonlLogger

    if cache is None:
        from planted.agent.cache import default_cache
        cache = default_cache()
    if run_fn is None:
        run_fn = _default_run_fn(engines if engines is not None else plan_runs(runs)[2])

    out = Path(out)
    done, bad = done_ids(out)
    seen, todo = set(done), []
    for r in runs:
        if r.episode_id not in seen:
            seen.add(r.episode_id)
            todo.append(r)
    logger = JsonlLogger(out)
    err_path = Path(errors_path)
    err_path.parent.mkdir(parents=True, exist_ok=True)
    err_lock = threading.Lock()
    stats = {"skipped_done": len(runs) - len(todo), "unreadable_lines": bad, "ok": 0, "errors": 0,
             "not_started": 0, "stopped_by_budget": False, "outcomes": Counter()}
    start_spent = cache.spent_usd

    def spent() -> float:
        return cache.spent_usd - start_spent

    def log_error(run, e: BaseException) -> None:
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "episode_id": run.episode_id, "grid": getattr(run, "grid", None),
               "error": f"{type(e).__name__}: {e}",
               "traceback": "".join(traceback.format_exception(e))[-2000:]}
        with err_lock, open(err_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def job(run):
        return run_fn(run, logger, cache)

    bar = tqdm(total=len(todo), disable=not progress, dynamic_ncols=True)
    finished = 0

    def report():
        msg = (f"[sweep] {finished}/{len(todo)} done; spent=${spent():.4f} "
               f"(cache hits={cache.hits} misses={cache.misses}); errors={stats['errors']}; "
               + " ".join(f"{k}={v}" for k, v in sorted(stats["outcomes"].items())))
        tqdm.write(msg) if progress else print(msg, flush=True)

    it = iter(todo)
    pending: dict = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            while len(pending) < workers:
                if max_usd is not None and spent() >= max_usd:
                    stats["stopped_by_budget"] = True
                    break
                r = next(it, None)
                if r is None:
                    break
                pending[pool.submit(job, r)] = r
            if not pending:
                break
            finished_now, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in finished_now:
                r = pending.pop(fut)
                try:
                    line = fut.result()
                    stats["ok"] += 1
                    stats["outcomes"][getattr(line, "outcome", "?")] += 1
                except Exception as e:  # noqa: BLE001 - log and keep going
                    stats["errors"] += 1
                    log_error(r, e)
                finished += 1
                bar.update(1)
                bar.set_postfix_str(f"${spent():.3f}")
                if report_every and finished % report_every == 0:
                    report()
            if stats["stopped_by_budget"] and not pending:
                break
    bar.close()
    stats["not_started"] = len(todo) - finished
    stats["spent_usd"] = spent()
    if stats["stopped_by_budget"]:
        msg = (f"[sweep] STOPPED: real spend ${spent():.4f} reached --max-usd {max_usd}; "
               f"{stats['not_started']} runs not started (rerun to resume)")
        tqdm.write(msg) if progress else print(msg, flush=True)
    report()
    return stats
