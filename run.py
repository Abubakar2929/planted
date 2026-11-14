# OWNER: A — see PLAN.md §2
"""Run a sweep: python run.py --arm A --model gemini-2.5-flash-lite --seed 0 [--defense none].

--dry-run prints the planned run count and exits without calling any model.
"""

from __future__ import annotations

import argparse

ARMS = ["A", "B", "D", "E", "G", "T4", "RW"]
DEFENSES = ["none", "prompt", "pagevote", "guard", "guard_noprov"]

# Placeholder sweep config for --dry-run. TODO (A): replace with the real grid from
# docs/plan-v2.2.md (Experiment design) once questions and doses are final.
CONFIG = {
    "n_questions": 20,  # dev20
    "doses_k": [0, 1, 3, 5, 10],
    "models": ["gemini-2.5-flash-lite", "groq/openai/gpt-oss-120b"],
    "seeds": [0],
    "defenses": ["none"],
}


def planned_runs(config: dict, models: list[str], seeds: list[int], defenses: list[str]) -> int:
    return config["n_questions"] * len(config["doses_k"]) * len(models) * len(seeds) * len(defenses)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, default="A")
    parser.add_argument("--model", default=None, help="default: every model in CONFIG")
    parser.add_argument("--seed", type=int, default=None, help="default: every seed in CONFIG")
    parser.add_argument("--defense", choices=DEFENSES, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    models = [args.model] if args.model else CONFIG["models"]
    seeds = [args.seed] if args.seed is not None else CONFIG["seeds"]
    defenses = [args.defense] if args.defense else CONFIG["defenses"]
    n = planned_runs(CONFIG, models, seeds, defenses)
    print(
        f"arm={args.arm} models={models} seeds={seeds} defenses={defenses} "
        f"planned_runs={n} est_cost_usd=TODO"
    )
    if args.dry_run:
        return 0
    # TODO (A, PLAN.md §8): load questions/pages, run planted.agent.loop.run_episode per
    # condition, append LogLines via planted.agent.logger, log spend to BUDGET.md.
    raise NotImplementedError("run.py: only --dry-run is implemented")


if __name__ == "__main__":
    raise SystemExit(main())
