# OWNER: C (written by B after C became unavailable; see PREREG.md §8)
"""Fill the Results / Discussion draft with numbers from `results/summary.json`.

    python -m analysis.fill_paper docs/paper_C.md --results results --out results/paper_C_filled.md

Placeholders look like `{{H1.estimate:.2f}}`, `{{G1.ci_lo:.0%}}`, `{{G3.estimate:.1pts}}` (percentage points), `{{G3.passed}}` or `{{runs}}`. A field
that is missing, None or NaN becomes `__` (AGENTS.md rule 9: never an estimate), and the script lists
every unresolved placeholder, so the draft can never claim a number that was not measured.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_]+)(?:\.([A-Za-z0-9_]+))?(?::([^}]+))?\s*\}\}")


def _lookup(summary: dict, key: str, field: str | None):
    hyp = summary.get("hypotheses", {})
    if field is None:
        return summary.get(key)
    h = hyp.get(key)
    if h is None:
        return None
    if field in ("ci_lo", "ci_hi"):
        ci = h.get("ci") or [None, None]
        return ci[0 if field == "ci_lo" else 1]
    return h.get(field)


def _fmt(v, spec: str | None) -> str | None:
    if v is None or v == "None":
        return None
    if isinstance(v, str):
        try:
            v = float(v) if v not in ("True", "False") else v == "True"
        except ValueError:
            return v
    if isinstance(v, bool):
        return "passed" if v else "not passed"
    if isinstance(v, float) and math.isnan(v):
        return None
    if spec and spec.endswith("pts"):  # difference of proportions shown in percentage points
        try:
            return format(100 * v, spec[:-3] + "f") + " pts"
        except (TypeError, ValueError):
            return None
    if spec:
        try:
            return format(v, spec)
        except (TypeError, ValueError):
            return None
    return str(v)


def fill(text: str, summary: dict) -> tuple[str, list[str]]:
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        out = _fmt(_lookup(summary, m.group(1), m.group(2)), m.group(3))
        if out is None:
            missing.append(m.group(0))
            return "__"
        return out

    return TOKEN.sub(sub, text), missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("draft", type=Path)
    ap.add_argument("--results", type=Path, default=Path("results"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    s = a.results / "summary.json"
    summary = json.loads(s.read_text(encoding="utf-8")) if s.exists() else {}
    text, missing = fill(a.draft.read_text(encoding="utf-8"), summary)
    out = a.out or a.results / (a.draft.stem + "_filled.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}; {len(missing)} placeholder(s) left as __")
    for m in sorted(set(missing)):
        print("  unresolved:", m, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
