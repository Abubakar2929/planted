# OWNER: B — see PLAN.md §2
"""Generate Contract-1 Questions and Pages as JSONL.

Usage: python -m data.generator.generate --seed 0 --split dev --tier T1 --out data/questions/
"""

from __future__ import annotations

import argparse
from pathlib import Path


def generate(seed: int, split: str, tier: str, out: Path) -> None:
    """TODO (B, PLAN.md §8): write Question + Page JSONL that validates against
    contracts/schemas.py. Randomised author/date/boilerplate in every tier; tiers T0, T1,
    T3, T4; benign syndication; honest single-origin voids; 15 fake-support-number brands
    (invented only). All domains fictional *.example."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--tier", choices=["T0", "T1", "T2", "T3", "T4"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    generate(args.seed, args.split, args.tier, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
