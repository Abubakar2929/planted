# OWNER: A — see PLAN.md §2
"""Run a sweep, one Contract-2 log line per run.

Grid mode (planted/sweep/grids.py; matches docs/plan-v2.2.md "Experiment design"):

    python run.py --arm A --grid pilot --workers 8 --max-usd 5 --out logs/pilot_A.jsonl
    python run.py --arm all --grid full --dry-run       # episodes and est. cost per arm

    --arm A (= A+B) | D | E | G | T4 | UG | all;  --model / --prompt-style override the grid's lists.

Legacy mode (no --grid): one model over --questions, as at Gate 1:

    python run.py --arm A --model gflite31 --seed 0 --defense none --mode single \\
        --bank data/pages/main --questions data/questions/dev20.jsonl --limit 1

Arm A legacy grid: k in {0,1,2,3,5,8} x label in {wire, propaganda, blog}, tier T1. Other arms need
explicit --k / --labels / --tiers. Combinations that data/pools.py rejects are skipped and counted.
--dry-run builds every pool, prints the run count and the estimated cost (EST_TOKENS_IN /
EST_TOKENS_OUT per run at pricing.py prices) and calls no model.

The --out file is appended to: episode ids already in it are skipped (resume). --overwrite empties
it first. Runs go through planted/sweep/runner.py: --workers threads (provider caps still apply),
errors to logs/errors.jsonl, --max-usd stops on real spend (cache misses only).
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from contracts.schemas import Condition

ARMS = ["A", "B", "D", "E", "G", "T4", "RW", "UG", "all"]
DEFENSES = ["none", "prompt", "pagevote", "guard", "guard_noprov"]
GRIDS = {"A": {"k": [0, 1, 2, 3, 5, 8], "labels": ["wire", "propaganda", "blog"], "tiers": ["T1"]}}
EST_TOKENS_IN = 2543   # measured mean at Gate 1 (single-call)
EST_TOKENS_OUT = 300
OUTCOMES = ("correct", "flip", "abstain_hedge", "drift")


def _csv(cast):
    return lambda s: [cast(x) for x in s.split(",") if x.strip()]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", choices=ARMS, default="A")
    p.add_argument("--grid", choices=["full", "pilot"], default=None,
                   help="use planted/sweep/grids.py (otherwise legacy single-model mode)")
    p.add_argument("--model", type=_csv(str), default=None,
                   help="roster alias(es), comma-separated; legacy default gflite31")
    p.add_argument("--prompt-style", type=_csv(str), default=None,
                   help="hedge_ok and/or neutral, comma-separated (default: grid's, else hedge_ok)")
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
    p.add_argument("--out", default=None, help="default logs/<arm>-<grid>.jsonl or logs/<arm>-<mode>-<model>-<defense>-s<seed>.jsonl")
    p.add_argument("--overwrite", action="store_true", help="empty --out first (default: append + resume)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-usd", type=float, default=None, help="stop when real spend reaches this")
    p.add_argument("--errors", default="logs/errors.jsonl")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def grid(args) -> tuple[list[int], list[str | None], list[str | None]]:
    g = GRIDS.get(args.arm, {})
    ks, labels, tiers = args.k or g.get("k"), args.labels or g.get("labels"), args.tiers or g.get("tiers")
    if ks is None or labels is None or tiers is None:
        raise SystemExit(f"arm {args.arm}: no default grid; pass --k, --labels and --tiers (or use --grid)")
    return ks, labels, tiers


def plan(engine, args, model: str) -> tuple[list[tuple], Counter]:
    """Legacy mode: [(question, condition)] that build a pool, and a Counter of skips."""
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


def _legacy_runs(args) -> tuple[list, Counter, dict, str]:
    from planted.engine import MockEngine
    from planted.providers import canonical_model
    from planted.sweep.grids import Run

    if args.arm in ("UG", "all"):
        raise SystemExit(f"--arm {args.arm} needs --grid full|pilot")
    engine = MockEngine.from_bank(args.bank, args.questions)
    runs, skipped = [], Counter()
    models = [canonical_model(m) for m in (args.model or ["gflite31"])]
    for model in models:
        pairs, sk = plan(engine, args, model)
        skipped += sk
        for st in args.prompt_style or ["hedge_ok"]:
            runs += [Run(args.arm, q, c, st, args.bank) for q, c in pairs]
    out = args.out or f"logs/{args.arm}-{args.mode}-{'+'.join(models)}-{args.defense}-s{args.seed}.jsonl"
    return runs, skipped, {args.bank: engine}, out


def _grid_runs(args) -> tuple[list, Counter, dict, str]:
    from planted.providers import canonical_model
    from planted.sweep.grids import GRIDS as SWEEP_GRIDS, build_grid
    from planted.sweep.runner import plan_runs

    names = SWEEP_GRIDS if args.arm == "all" else ["A" if args.arm == "B" else args.arm]
    if any(n not in SWEEP_GRIDS for n in names):
        raise SystemExit(f"--arm {args.arm}: no sweep grid (grids: {SWEEP_GRIDS})")
    models = [canonical_model(m) for m in args.model] if args.model else None
    runs, notes = [], []
    for n in names:
        try:
            r, nt = build_grid(n, args.grid, styles=args.prompt_style, models=models, seed=args.seed)
        except SystemExit as e:
            if args.arm != "all":
                raise
            print(f"  {n}: {e}")
            continue
        runs += r
        notes += nt
    for n in dict.fromkeys(notes):
        print(n)
    valid, skipped, engines = plan_runs(runs)
    out = args.out or f"logs/{args.arm}-{args.grid}.jsonl"
    return valid, skipped, engines, out


def _print_plan(args, runs, skipped) -> None:
    from planted.agent.pricing import cost_usd
    from planted.providers import resolve_model

    def est(m):
        return cost_usd(resolve_model(m), EST_TOKENS_IN, EST_TOKENS_OUT)

    total = sum(est(r.cond.model) for r in runs)
    models = sorted({r.cond.model for r in runs})
    print(f"arm={args.arm} grid={args.grid or 'legacy'} mode={args.mode} model={','.join(models)} "
          f"seed={args.seed} defense={args.defense if not args.grid else 'grid'} "
          f"planned_runs={len(runs)} skipped={sum(skipped.values())} est_cost_usd={total:.4f} "
          f"(at {EST_TOKENS_IN} in / {EST_TOKENS_OUT} out tokens per run)")
    by = Counter((r.grid, r.cond.model) for r in runs)
    for g in dict.fromkeys(r.grid for r in runs):
        n = sum(v for (gg, _), v in by.items() if gg == g)
        c = sum(v * est(m) for (gg, m), v in by.items() if gg == g)
        per = " ".join(f"{m}={v}" for (gg, m), v in sorted(by.items()) if gg == g)
        print(f"  grid {g}: episodes={n} est_cost_usd={c:.4f} ({per})")
    shown = list(skipped.items())
    for why, v in shown[:20]:
        print(f"  skip {why}" + (f" x{v}" if v > 1 else ""))
    if len(shown) > 20:
        print(f"  ... {len(shown) - 20} more skip reasons")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "agent":
        raise NotImplementedError("--mode agent: the tool loop (planted/agent/loop.py) is not done; use --mode single")
    if args.prompt_style:
        from planted.agent.single_call import PROMPT_STYLES
        bad = [s for s in args.prompt_style if s not in PROMPT_STYLES]
        if bad:
            raise SystemExit(f"unknown --prompt-style {bad}; expected {list(PROMPT_STYLES)}")

    runs, skipped, engines, out = _grid_runs(args) if args.grid else _legacy_runs(args)
    _print_plan(args, runs, skipped)
    if args.dry_run:
        return 0

    from planted.agent.cache import default_cache
    from planted.sweep.runner import run_sweep

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.overwrite:
        out.write_text("", encoding="utf-8")
    cache = default_cache()
    stats = run_sweep(runs, out, workers=args.workers, max_usd=args.max_usd, cache=cache,
                      engines=engines, errors_path=args.errors)
    o = stats["outcomes"]
    print(f"n={stats['ok']} " + " ".join(f"{k}={o[k]}" for k in OUTCOMES)
          + f" errors={stats['errors']} resumed_skip={stats['skipped_done']} not_started={stats['not_started']}")
    print(f"cost_usd spent={cache.spent_usd:.6f} cache hits={cache.hits} misses={cache.misses} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
