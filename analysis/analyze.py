# OWNER: C — see PLAN.md §2
"""`python -m analysis.analyze logs/`: rebuild every figure and Table 1 from logs alone."""

from __future__ import annotations

import argparse
from pathlib import Path


def analyze(logs_dir: Path, out_dir: Path) -> None:
    """TODO (C, PLAN.md §8): load logs/*.jsonl as LogLines, score, run stats, write
    results/*.csv and figures."""
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs_dir", type=Path)
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args(argv)
    analyze(args.logs_dir, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
