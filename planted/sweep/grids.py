# OWNER: A — see PLAN.md §2
"""Run grids for every arm, matching docs/plan-v2.2.md "Experiment design" and the 3-model roster.

    runs, notes = build_grid("A", "full")      # -> list[Run], list[str] (warnings / notes)

| grid | full | pilot (dev split only) |
|---|---|---|
| A  | 120 Q (dev20 + test) x [k=0 + k in {1,2,3,5,8} x {wire, propaganda, blog}] T1 x 3 models = 5,760 | dev20 x k in {0,1,2,3,5,8} x 3 labels (k=0 per label) x {gflite31, gptoss} x {hedge_ok, neutral} = 1,440 |
| D  | hedge150 x source_hedge {none, may, preliminary, disagree} x n_agree {1, 3} x 3 models = 3,600 | 20 dev hedge Q x 8 x 2 models = 320 |
| E  | urdu60 + matching EN qids x [k=0; k in {3,8} x {wire, propaganda}] T1 x {gflite31, gptoss} = 1,200 | not defined (no dev Urdu questions) |
| G  | 120 Q x 10 conditions x 5 defences x {gflite31, gptoss} (see below) | dev20 (+ dev -so/-syn variants), main bank |
| T4 | 20 test Q with T4 pages x k in {3,8} x {none, guard} x gflite31 = 80 | not defined |
| UG | urdu60 x k in {0,3,8} (T1) x {none, guard} x gflite31 = 360 | not defined |

G's 10 conditions: k=0 clean; honest single-origin (the ``-so`` question, k=0); benign syndication (the
``-syn`` question, k=0); T0, T1, T3 x k in {3, 8}; T1 k=5. The -so/-syn variants exist only for known and
support facts (95 of 120), so void questions get 8 conditions: (120 x 8 + 95 x 2) x 5 x 2 = 11,500, not
the plan's nominal 12,000. Test questions in G, T4 and UG use the held-out bank (data/heldout/pages) when
it exists; otherwise the main bank, with a loud warning (PLAN.md §6: say so in the paper).

Contract arms: A+B runs are logged as arm "A" (labels distinguish B); UG is logged as arm "G" with
lang "ur" (no UG literal in contracts) and ``grid=UG`` in guard_summary.
Every run's guard_summary carries ``grid=<name>``. Seeds are fixed (default 0).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from contracts.schemas import Condition, Question

ROOT = Path(__file__).resolve().parents[2]
QDIR = ROOT / "data" / "questions"
BANK_MAIN = ROOT / "data" / "pages" / "main"
BANK_HELDOUT = ROOT / "data" / "heldout" / "pages"

EST_TOKENS_IN = 2543   # measured mean per single-call run at Gate 1
EST_TOKENS_OUT = 300

GRIDS = ["A", "D", "E", "G", "T4", "UG"]
BENCH_MODELS = ["gflite31", "gptoss", "gptoss20"]
GUARD_MODELS = ["gflite31", "gptoss"]
DEFENSES = ["none", "prompt", "pagevote", "guard", "guard_noprov"]
DOSES = [1, 2, 3, 5, 8]
LABELS = ["wire", "propaganda", "blog"]
HEDGES = ["none", "may", "preliminary", "disagree"]
N_AGREE = [1, 3]
PILOT_MODELS = ["gflite31", "gptoss"]
PILOT_STYLES = ["hedge_ok", "neutral"]


@dataclass(eq=False)
class Run:
    grid: str
    question: Question
    cond: Condition
    style: str
    bank: str
    _eid: str | None = field(default=None, repr=False)

    @property
    def episode_id(self) -> str:
        if self._eid is None:
            from planted.agent.single_call import episode_id_for

            self._eid = episode_id_for(self.cond, self.question.qid, self.style)
        return self._eid

    @property
    def tag(self) -> str:
        return f"grid={self.grid}"


def load_q(name: str) -> list[Question]:
    path = QDIR / f"{name}.jsonl"
    return [Question.model_validate_json(l) for l in open(path, encoding="utf-8") if l.strip()]


def _cond(arm, k, label, tier, lang, defense, model, seed, hedge=None, n_agree=None) -> Condition:
    return Condition(arm=arm, k=k, label=label, tier=tier, lang=lang, source_hedge=hedge,
                     n_agree=n_agree, defense=defense, model=model, seed=seed)


def _heldout_present() -> bool:
    return (BANK_HELDOUT / "pages.jsonl").exists() and (BANK_HELDOUT / "index.jsonl").exists()


def _guard_bank(q: Question, notes: list[str]) -> str:
    """Held-out bank for test questions when present, else the main bank (warned once)."""
    if q.split == "test":
        if _heldout_present():
            return str(BANK_HELDOUT)
        msg = ("WARNING: data/heldout/pages missing; Guard-arm TEST questions use the MAIN bank. "
               "Say so in the paper (PLAN.md §6).")
        if msg not in notes:
            notes.append(msg)
    return str(BANK_MAIN)


def _variants(base: list[Question], name: str, suffix: str) -> dict[str, Question]:
    """base qid -> its -so / -syn question."""
    return {q.qid.removesuffix(suffix): q for q in load_q(name)}


def build_grid(name: str, size: str = "full", styles: list[str] | None = None,
               models: list[str] | None = None, seed: int = 0) -> tuple[list[Run], list[str]]:
    """All runs of one grid (pool validity is checked later, by the runner's planner)."""
    if name not in GRIDS:
        raise ValueError(f"unknown grid {name!r}; expected one of {GRIDS}")
    if size not in ("full", "pilot"):
        raise ValueError("size must be 'full' or 'pilot'")
    pilot = size == "pilot"
    notes: list[str] = []
    styles = styles or (PILOT_STYLES if pilot else ["hedge_ok"])
    main = str(BANK_MAIN)
    runs: list[Run] = []

    def add(q, c, bank):
        for m in models_used:
            for st in styles:
                runs.append(Run(name, q, c.model_copy(update={"model": m}), st, bank))

    if name == "A":
        models_used = models or (PILOT_MODELS if pilot else BENCH_MODELS)
        qs = load_q("dev20") if pilot else load_q("dev20") + load_q("test")
        for q in qs:
            if pilot:  # Gate 1 / run.py layout: k=0 once per label
                conds = [_cond("A", k, lab, "T1", q.lang, "none", "_", seed)
                         for k in [0, *DOSES] for lab in LABELS]
            else:
                conds = [_cond("A", 0, None, "T1", q.lang, "none", "_", seed)]
                conds += [_cond("A", k, lab, "T1", q.lang, "none", "_", seed) for k in DOSES for lab in LABELS]
            for c in conds:
                add(q, c, main)

    elif name == "D":
        models_used = models or (PILOT_MODELS if pilot else BENCH_MODELS)
        qs = [q for q in load_q("hedge150") if not pilot or q.split == "dev"]
        for q in qs:
            for h in HEDGES:
                for n in N_AGREE:
                    add(q, _cond("D", 0, None, None, q.lang, "none", "_", seed, h, n), main)

    elif name == "E":
        if pilot:
            raise SystemExit("grid E: no dev-split Urdu questions, so no pilot (AGENTS.md rule 8)")
        models_used = models or GUARD_MODELS
        ur = load_q("urdu60")
        en_all = {q.qid: q for q in load_q("dev20") + load_q("test")}
        missing = [q.qid for q in ur if q.qid.removesuffix("-ur") not in en_all]
        if missing:
            notes.append(f"grid E: {len(missing)} Urdu qids have no EN match: {missing[:5]}")
        qs = ur + [en_all[q.qid.removesuffix("-ur")] for q in ur if q.qid.removesuffix("-ur") in en_all]
        for q in qs:
            conds = [_cond("E", 0, None, None, q.lang, "none", "_", seed)]
            conds += [_cond("E", k, lab, "T1", q.lang, "none", "_", seed) for k in (3, 8) for lab in ("wire", "propaganda")]
            for c in conds:
                add(q, c, main)

    elif name == "G":
        models_used = models or GUARD_MODELS
        base = load_q("dev20") if pilot else load_q("dev20") + load_q("test")
        so = _variants(base, "single_origin", "-so")
        syn = _variants(base, "syndication", "-syn")
        for q in base:
            bank = _guard_bank(q, notes) if not pilot else main
            items = [(q, 0, None)]
            if q.qid in so:
                items.append((so[q.qid], 0, None))
            if q.qid in syn:
                items.append((syn[q.qid], 0, None))
            items += [(q, k, t) for t in ("T0", "T1", "T3") for k in (3, 8)] + [(q, 5, "T1")]
            for qq, k, tier in items:
                for dfn in DEFENSES:
                    add(qq, _cond("G", k, None, tier, qq.lang, dfn, "_", seed), bank)

    elif name == "T4":
        if pilot:
            raise SystemExit("grid T4: test questions only, so no pilot (AGENTS.md rule 8)")
        models_used = models or ["gflite31"]
        bank_dir = BANK_HELDOUT if _heldout_present() else BANK_MAIN
        if bank_dir == BANK_MAIN:
            _guard_bank(Question(qid="x", lang="en", split="test", regime="known", question="x",
                                 correct_answer="x", planted_answer=None), notes)
        with_t4 = {r["qid"] for r in map(json.loads, open(bank_dir / "index.jsonl", encoding="utf-8"))
                   if r.get("role") == "planted" and r.get("tier") == "T4"}
        qs = [q for q in load_q("test") if q.qid in with_t4][:20]
        if len(qs) < 20:
            notes.append(f"grid T4: only {len(qs)} test questions have T4 pages in {bank_dir}")
        for q in qs:
            for k in (3, 8):
                for dfn in ("none", "guard"):
                    add(q, _cond("T4", k, None, "T4", q.lang, dfn, "_", seed), str(bank_dir))

    elif name == "UG":
        if pilot:
            raise SystemExit("grid UG: test questions only, so no pilot (AGENTS.md rule 8)")
        models_used = models or ["gflite31"]
        for q in load_q("urdu60"):
            bank = _guard_bank(q, notes)
            for k in (0, 3, 8):
                for dfn in ("none", "guard"):
                    add(q, _cond("G", k, None, "T1" if k else None, q.lang, dfn, "_", seed), bank)

    return runs, notes


def est_cost_per_run(model: str) -> float:
    from planted.agent.pricing import cost_usd
    from planted.providers import resolve_model

    return cost_usd(resolve_model(model), EST_TOKENS_IN, EST_TOKENS_OUT)
