# OWNER: A — see PLAN.md §2
"""Run a sweep, one Contract-2 log line per run.

    python run.py --arm A --model gflite31 --seed 0 --defense none --mode single \\
        --bank data/pages/main --questions data/questions/dev20.jsonl --limit 1

Arm A (PREREG.md §2): k in {0,1,2,3,5,8} x label in {wire, propaganda, blog}, tier T1.
Other arms need explicit --k / --labels / --tiers (arm D's hedge grid is not wired up yet).
Combinations that data/pools.py rejects (e.g. a T1/blog campaign missing for an Urdu question)
are skipped and counted. --dry-run builds every pool, prints the run count and the estimated
cost (EST_TOKENS_IN / EST_TOKENS_OUT per run at pricing.py prices) and calls no model.
The --out file is overwritten; reruns are free because every call goes through the cache.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from contracts.schemas import Condition

ARMS = ["A", "B", "D", "E", "G", "T4", "RW"]
DEFENSES = ["none", "prompt", "pagevote", "guard", "guard_noprov"]
GRIDS = {"A": {"k": [0, 1, 2, 3, 5, 8], "labels": ["wire", "propaganda", "blog"], "tiers": ["T1"]}}
EST_TOKENS_IN = 6000
EST_TOKENS_OUT = 300
OUTCOMES = ("correct", "flip", "abstain_hedge", "drift")


def _csv(cast):
    return lambda s: [cast(x) for x in s.split(",") if x.strip()]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", choices=ARMS, default="A")
    p.add_argument("--model", default="gflite31", help="roster alias or any long form")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--defense", choices=DEFENSES, default="none")
    p.add_argument("--mode", choices=["single", "agent"], default="single")
    p.add_argument("--bank", default="data/pages/main")
    p.add_argument("--questions", nargs="+", default=["data/questions/dev20.jsonl"])
    p.add_argument("--limit", type=int, default=None, help="first N questions (after --lang)")
    p.add_argument("--k", type=_csv(int), default=None, help="e.g. 0,3,8")
    p.add_argument("--labels", type=_csv(str), default=None, help="e.g. wire,blog")
    p.add_argument("--tiers", type=_csv(str), default=None, help="e.g. T1")
    p.add_argument("--lang", choices=["en", "ur"], default=None, help="only questions in this language")
    p.add_argument("--out", default=None, help="default logs/<arm>-<mode>-<model>-<defense>-s<seed>.jsonl")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def grid(args) -> tuple[list[int], list[str | None], list[str | None]]:
    g = GRIDS.get(args.arm, {})
    ks, labels, tiers = args.k or g.get("k"), args.labels or g.get("labels"), args.tiers or g.get("tiers")
    if ks is None or labels is None or tiers is None:
        raise SystemExit(f"arm {args.arm}: no default grid; pass --k, --labels and --tiers")
    return ks, labels, tiers


def plan(engine, args, model: str) -> tuple[list[tuple], Counter]:
    """[(question, condition)] that build a pool, and a Counter of skipped combinations."""
    from planted.engine import PoolError

    ks, labels, tiers = grid(args)
    qs = [q for q in engine.questions.values() if args.lang is None or q.lang == args.lang]
    qs = qs[: args.limit] if args.limit is not None else qs
    runs, skipped = [], Counter()
    for q in qs:
        for k in ks:
            for label in labels:
                for tier in tiers:
                    c = Condition(arm=args.arm, k=k, label=label, tier=tier, lang=q.lang,
                                  source_hedge=None, n_agree=None, defense=args.defense,
                                  model=model, seed=args.seed)
                    try:
                        engine.build_pool(q, c)
                    except PoolError as e:
                        skipped[f"{q.qid} k={k} {tier}/{label}: {e}"] += 1
                        continue
                    runs.append((q, c))
    return runs, skipped


def main(argv: list[str] | None = None) -> int:
    from planted.agent.pricing import cost_usd
    from planted.providers import canonical_model, resolve_model

    args = parse_args(argv)
    model = canonical_model(args.model)
    est_each = cost_usd(resolve_model(model), EST_TOKENS_IN, EST_TOKENS_OUT)
    if args.mode == "agent":
        raise NotImplementedError("--mode agent: the tool loop (planted/agent/loop.py) is not done; use --mode single")

    from planted.engine import MockEngine

    engine = MockEngine.from_bank(args.bank, args.questions)
    runs, skipped = plan(engine, args, model)
    print(f"arm={args.arm} mode={args.mode} model={model} seed={args.seed} defense={args.defense} "
          f"planned_runs={len(runs)} skipped={sum(skipped.values())} "
          f"est_cost_usd={len(runs) * est_each:.4f} "
          f"(at {EST_TOKENS_IN} in / {EST_TOKENS_OUT} out tokens per run)")
    for why in skipped:
        print(f"  skip {why}")
    if args.dry_run:
        return 0

    from planted.agent.cache import default_cache
    from planted.agent.logger import JsonlLogger
    from planted.agent.single_call import run_single

    out = Path(args.out or f"logs/{args.arm}-{args.mode}-{model}-{args.defense}-s{args.seed}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("", encoding="utf-8")
    logger, cache = JsonlLogger(out), default_cache()
    counts, logged_cost, tok_in = Counter(), 0.0, 0
    for q, c in runs:
        line = run_single(engine, q, c, logger, cache=cache)
        counts[line.outcome] += 1
        logged_cost += line.cost_usd
        tok_in += line.tokens_in
    n = len(runs)
    print(f"n={n} " + " ".join(f"{o}={counts[o]}" for o in OUTCOMES))
    print(f"cost_usd spent={cache.spent_usd:.6f} logged={logged_cost:.6f} "
          f"cache hits={cache.hits} misses={cache.misses} "
          f"tokens_in/run={tok_in / n if n else 0:.0f} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
