# OWNER: A — see PLAN.md §2
"""`planted` console script: run, serve, analyze."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="planted")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="run a sweep (see run.py)")
    serve = sub.add_parser("serve", help="gpt-researcher proxy")
    serve.add_argument("--guard", action="store_true")
    analyze = sub.add_parser("analyze", help="rebuild figures and tables from logs")
    analyze.add_argument("logs_dir", nargs="?", default="logs")
    return parser


def main(argv: list[str] | None = None) -> int:
    """TODO (A, PLAN.md §8): wire subcommands to run.py, planted.serve and analysis.analyze."""
    args = build_parser().parse_args(argv)
    print(f"{args.command}: not implemented yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
