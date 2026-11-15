# OWNER: A — see PLAN.md §2
"""Stage the Planted dataset for the Hugging Face Hub, check it, and (only with --push) upload it.

    python scripts/push_hf_dataset.py --repo ORG/NAME            # dry run (default): list, size, checks
    python scripts/push_hf_dataset.py --repo ORG/NAME --push     # upload; prints the commit SHA

Collected (output files only, never generator code):
    data/questions/*.jsonl
    data/pages/main/{pages,index}.jsonl, data/pages/main/manifest.json
    data/heldout/pages/{pages,index}.jsonl, manifest.json
    data/lexicons/*.json
    results/*.csv (if any)

Checks, run before anything is staged (any failure aborts):
    1. every page url (pages.jsonl and index.jsonl) and every page `domain` ends with ".example";
    2. no file contains "API_KEY", a Google API key (AIza...) or a Groq key (gsk_...).

A dataset card (README.md) is written next to the files in a temporary folder. --push uploads that
folder with huggingface_hub.HfApi().upload_folder (token: HF_TOKEN or `hf auth login`) and prints the
commit SHA, so the paper can cite a pinned revision. Raw run logs are not part of this script.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "API_KEY": re.compile(r"API_KEY"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Groq API key": re.compile(r"gsk_[0-9A-Za-z]{20,}"),
}
PAGE_FILES = ("pages.jsonl", "index.jsonl")

CARD = """---
license: mit
language:
- en
- ur
pretty_name: Planted
tags:
- search-agents
- data-poisoning
- misinformation
- retrieval
size_categories:
- 10K<n<100K
---

# Planted: a mock web for measuring and fixing poisoned search results

Questions and a fictional, deterministic page bank used to measure how AI search agents respond
to coordinated planted pages (dose, source label, data voids, source hedges, English and Urdu),
and to evaluate Planted Guard, a retrieval-time defence that counts independent origins
instead of pages. Code: the `planted` repository (run.py, planted/engine, data/pools.py).

**Everything here is fictional.** Every site is on the reserved `.example` domain. Entities,
outlets, people, brands and phone numbers are invented. No page imitates a real outlet, person,
brand or government body. Do not use these pages as facts.

## Files

{files}

## Fields

`data/questions/*.jsonl`, one question per line:
`qid`, `lang` (en|ur), `split` (dev|test), `regime` (known|void|support|single_origin|syndication|hedge),
`question`, `correct_answer`, `planted_answer`.

`data/pages/main/pages.jsonl` (main bank) and `data/heldout/pages/pages.jsonl` (held-out bank,
written separately for the Guard evaluation), one page per line:
`url`, `domain`, `title`, `snippet`, `body`, `lang`, `author`, `date`, and the scoring-only fields
hidden from agents: `planted`, `campaign_id`, `label` (wire|propaganda|blog|official|neutral),
`tier` (T0–T4), `asserted_answer`, `source_hedge`.

`index.jsonl` maps each page to its question and role:
`qid`, `role` (planted|honest|filler|official|syndicated|hedge), `tier`, `label`, `hedge`, `slot`,
`lang`, `gen`, `url`. `manifest.json` records how each bank was generated (`written_by`).

`data/lexicons/hedge_{{en,ur}}.json`: hedge and disagreement markers at four levels
(none < may < preliminary < disagree). `results/*.csv` (when present): aggregate results from
`python -m analysis.analyze logs/`.

Pools of 10 results per condition are built by `data/pools.py` in the code repository.

## License

MIT.

## Citation

```
@misc{{planted2026,
  title  = {{Planted: __}},
  author = {{__}},
  year   = {{2026}},
  note   = {{Dataset revision __}}
}}
```
"""


class CheckError(AssertionError):
    pass


def collect(root: Path = ROOT) -> list[Path]:
    """Files to publish, as paths relative to root (sorted, existing only)."""
    pats = ["data/questions/*.jsonl",
            "data/pages/main/pages.jsonl", "data/pages/main/index.jsonl", "data/pages/main/manifest.json",
            "data/heldout/pages/pages.jsonl", "data/heldout/pages/index.jsonl",
            "data/heldout/pages/manifest.json",
            "data/lexicons/*.json", "results/*.csv"]
    out: set[Path] = set()
    for pat in pats:
        out.update(p.relative_to(root) for p in root.glob(pat) if p.is_file())
    return sorted(out)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def check_domains(root: Path, files: list[Path]) -> int:
    """Every url / domain in page files ends with .example. Returns the number of urls checked."""
    n = 0
    for rel in files:
        if rel.name not in PAGE_FILES:
            continue
        for i, line in enumerate(open(root / rel, encoding="utf-8"), start=1):
            if not line.strip():
                continue
            rec = json.loads(line)
            url = rec.get("url", "")
            if not _host(url).endswith(".example"):
                raise CheckError(f"{rel}:{i}: url domain is not .example: {url!r}")
            dom = rec.get("domain")
            if dom is not None and not str(dom).lower().endswith(".example"):
                raise CheckError(f"{rel}:{i}: domain is not .example: {dom!r}")
            n += 1
    return n


def check_secrets(root: Path, files: list[Path]) -> None:
    for rel in files:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        for what, pat in SECRET_PATTERNS.items():
            m = pat.search(text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                raise CheckError(f"{rel}:{line}: contains {what}")


def run_checks(root: Path = ROOT, files: list[Path] | None = None) -> dict:
    files = collect(root) if files is None else files
    if not files:
        raise CheckError("no files collected")
    urls = check_domains(root, files)
    check_secrets(root, files)
    return {"files": len(files), "urls_checked": urls}


def stage(root: Path, files: list[Path], dest: Path) -> None:
    for rel in files:
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest / rel)
    listing = "\n".join(f"- `{rel.as_posix()}`" for rel in files)
    (dest / "README.md").write_text(CARD.format(files=listing), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True, help="Hub dataset repo, ORG/NAME")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="default: list and check only")
    mode.add_argument("--push", action="store_true", help="upload to the Hub")
    args = p.parse_args(argv)
    if "/" not in args.repo:
        p.error("--repo must look like ORG/NAME")

    files = collect(ROOT)
    try:
        stats = run_checks(ROOT, files)
    except CheckError as e:
        print(f"CHECK FAILED: {e}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="planted_hf_") as tmp:
        dest = Path(tmp)
        stage(ROOT, files, dest)
        staged = sorted(q for q in dest.rglob("*") if q.is_file())
        total = sum(q.stat().st_size for q in staged)
        for q in staged:
            print(f"{q.stat().st_size:>12,}  {q.relative_to(dest).as_posix()}")
        print(f"{len(staged)} files, {total / 1e6:.2f} MB -> dataset {args.repo}")
        print(f"checks passed: {stats['urls_checked']:,} page urls end in .example; "
              f"no API_KEY / Google / Groq key strings in {stats['files']} files")
        if not args.push:
            print("dry run: nothing uploaded (pass --push to upload)")
            return 0
        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(args.repo, repo_type="dataset", exist_ok=True)
        info = api.upload_folder(folder_path=str(dest), repo_id=args.repo, repo_type="dataset",
                                 commit_message="Planted dataset upload")
        print(f"pushed: https://huggingface.co/datasets/{args.repo} commit {info.oid} "
              f"(pin with revision={info.oid})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
