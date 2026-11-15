# OWNER: A — see PLAN.md §2
"""`planted` console script.

    planted serve --port 8000 --host 127.0.0.1
    planted guard --query "Q" --results results.json --lang en
    planted run --arm A --grid pilot --dry-run       # same flags as python run.py
    planted analyze logs/ --out results
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="planted")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a sweep: every flag goes to run.py (see python run.py -h)",
                         add_help=False)
    run.add_argument("args", nargs=argparse.REMAINDER)
    serve = sub.add_parser("serve", help="gpt-researcher custom-retriever proxy (planted/serve.py)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    g = sub.add_parser("guard", help="run guard() on a JSON list of results and print the result")
    g.add_argument("--query", required=True)
    g.add_argument("--results", required=True, help="JSON file: list of {url, title, snippet, content, rank}")
    g.add_argument("--lang", default="en", choices=["en", "ur"])
    analyze = sub.add_parser("analyze", help="rebuild figures and tables from logs")
    analyze.add_argument("logs_dir", nargs="?", default="logs")
    analyze.add_argument("--out", default="results")
    return parser


def _run(argv: list[str]) -> int:
    path = ROOT / "run.py"
    if not path.exists():
        print("run.py not found next to the package (installed without the repo?). Equivalent command:\n"
              f"  python run.py {' '.join(argv)}")
        return 2
    spec = importlib.util.spec_from_file_location("planted_run", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod.main(argv)


def _guard(query: str, results_path: str, lang: str) -> int:
    try:
        results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {results_path}: {e}", file=sys.stderr)
        return 2
    if not isinstance(results, list):
        print(f"{results_path}: expected a JSON list of result objects", file=sys.stderr)
        return 2
    from planted.guard import guard

    try:
        out = guard(query, results, lang)
    except NotImplementedError:
        print("Guard not implemented yet", file=sys.stderr)
        return 1
    print(out.model_dump_json(indent=2) if hasattr(out, "model_dump_json") else json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["run"]:  # pass every flag through untouched (argparse would reject --arm etc.)
        return _run(argv[1:])
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        from planted.serve import serve

        serve(host=args.host, port=args.port)
        return 0
    if args.command == "guard":
        return _guard(args.query, args.results, args.lang)
    if args.command == "analyze":
        from analysis.analyze import main as analyze_main

        return analyze_main([args.logs_dir, "--out", args.out]) or 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
