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

**Free-tier grid** (``build_free(part)`` or ``build_grid(part, "free")``; TEST split only, prompt style
``neutral`` as preregistered, model gflite31 unless stated; questions picked by ``stratified()``: a
seed-0 shuffle of the qid-sorted list within each regime, quotas by largest remainder, so smaller
picks nest inside larger ones):

| part | runs | layout |
|---|---|---|
| P1 AB  | 960 | 60 test Q x [k=0 + k in {1,2,3,5,8} x {wire, propaganda, blog}] T1, main bank (arm A) |
| P2 G   | 800 | 40 test Q x {k=0 clean; T0 k=3; T1 k=3; T1 k=5; single_origin k=0} x {none, prompt, pagevote, guard}, held-out bank |
| P3 REP | 180 | gptoss, 20 of the 40: [k=0; k in {3,8} x {wire, propaganda}] (A, main) + {none, guard} x {T0 k=3, T1 k=3} (G, held-out) |
| P4 UR  | 180 | 30 urdu60 Q + their EN counterparts x [k=0; k in {3,8} x wire] T1, main bank (arm E) |
| P5 D   | 320 | 40 test hedge150 claims x source_hedge {none, may, preliminary, disagree} x n_agree {1, 3}, main bank |
| P6 G2  | 480 | the 40 of P2 x {T3 k=3, T3 k=8, T0 k=8, T1 k=8} x {none, pagevote, guard}, held-out bank |

Substitutions (counted in the notes): void questions have no ``-so`` variant, so P2's single_origin
cell for a void question uses the next unused non-void test question's ``-so`` variant (seed-0 order).
A question whose pool is rejected for any of its part's conditions is replaced by the next unused
question of the same regime (``plan_free``).

Contract arms: A+B runs are logged as arm "A" (labels distinguish B); UG is logged as arm "G" with
lang "ur" (no UG literal in contracts) and ``grid=UG`` in guard_summary.
Every run's guard_summary carries ``grid=<name>``. Seeds are fixed (default 0).
"""

from __future__ import annotations

import json
import random
from collections import Counter
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
FREE_PARTS = ["P1", "P2", "P3", "P4", "P5", "P6"]
FREE_NAMES = {"P1": "AB", "P2": "G", "P3": "REP", "P4": "UR", "P5": "D", "P6": "G2"}
FREE_SIZES = {"P1": 960, "P2": 800, "P3": 180, "P4": 180, "P5": 320, "P6": 480}
FREE_TONIGHT = ["P1", "P2", "P3"]
FREE_STYLE = "neutral"   # PREREG.md §2: agent prompt style for all arms


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
    if size == "free":
        return build_free(name, seed=seed)
    if name not in GRIDS:
        raise ValueError(f"unknown grid {name!r}; expected one of {GRIDS}")
    if size not in ("full", "pilot"):
        raise ValueError("size must be 'full', 'pilot' or 'free'")
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


# =========================================================================== free-tier grid
def _quotas(sizes: dict[str, int], n: int) -> dict[str, int]:
    """Largest-remainder split of n over strata; ties go to the larger stratum, then by name."""
    total = sum(sizes.values())
    if n > total:
        raise ValueError(f"asked for {n} questions, only {total} available")
    exact = {r: n * c / total for r, c in sizes.items()}
    q = {r: int(x) for r, x in exact.items()}
    order = sorted(sizes, key=lambda r: (-(exact[r] - q[r]), -sizes[r], r))
    for r in order[: n - sum(q.values())]:
        q[r] += 1
    return q


def regime_order(qs: list[Question], seed: int = 0) -> dict[str, list[Question]]:
    """regime -> its questions, qid-sorted then shuffled with Random(f"{seed}:{regime}")."""
    by: dict[str, list[Question]] = {}
    for q in sorted(qs, key=lambda q: q.qid):
        by.setdefault(q.regime, []).append(q)
    for r, lst in by.items():
        random.Random(f"{seed}:{r}").shuffle(lst)
    return by


def stratified(qs: list[Question], n: int, seed: int = 0) -> list[Question]:
    """n questions, stratified by regime (deterministic; smaller n nests in larger n). qid-sorted."""
    by = regime_order(qs, seed)
    quota = _quotas({r: len(v) for r, v in by.items()}, n)
    return sorted((q for r, v in by.items() for q in v[: quota[r]]), key=lambda q: q.qid)


def _test_only(qs: list[Question], what: str) -> list[Question]:
    bad = [q.qid for q in qs if q.split != "test"]
    if bad:
        raise AssertionError(f"{what}: non-test questions {bad[:5]}")
    return qs


def _free_questions(seed: int = 0) -> dict:
    """The question picks shared by the parts (all test split)."""
    test = _test_only(load_q("test"), "test.jsonl")
    hedge = [q for q in load_q("hedge150") if q.split == "test"]
    ur = _test_only(load_q("urdu60"), "urdu60")
    return {"test": test, "q60": stratified(test, 60, seed), "q40": stratified(test, 40, seed),
            "q20": stratified(test, 20, seed), "ur30": stratified(ur, 30, seed),
            "hedge40": stratified(hedge, 40, seed)}


def _free_items(part: str, qs: list[Question], extra: dict, seed: int) -> list[tuple]:
    """[(question, condition-without-model, bank)] for one base question of a part."""
    c, main, held = _cond, str(BANK_MAIN), str(BANK_HELDOUT)
    out = []
    for q in qs:
        L = q.lang
        if part == "P1":
            out.append((q, c("A", 0, None, "T1", L, "none", "gflite31", seed), main))
            out += [(q, c("A", k, lab, "T1", L, "none", "gflite31", seed), main)
                    for k in DOSES for lab in LABELS]
        elif part == "P2":
            so = extra["so"][q.qid]
            for dfn in ("none", "prompt", "pagevote", "guard"):
                out.append((q, c("G", 0, None, None, L, dfn, "gflite31", seed), held))
                out += [(q, c("G", k, None, t, L, dfn, "gflite31", seed), held)
                        for t, k in (("T0", 3), ("T1", 3), ("T1", 5))]
                out.append((so, c("G", 0, None, None, so.lang, dfn, "gflite31", seed), held))
        elif part == "P3":
            out.append((q, c("A", 0, None, "T1", L, "none", "gptoss", seed), main))
            out += [(q, c("A", k, lab, "T1", L, "none", "gptoss", seed), main)
                    for k in (3, 8) for lab in ("wire", "propaganda")]
            out += [(q, c("G", k, None, t, L, dfn, "gptoss", seed), held)
                    for dfn in ("none", "guard") for t, k in (("T0", 3), ("T1", 3))]
        elif part == "P4":
            out.append((q, c("E", 0, None, None, L, "none", "gflite31", seed), main))
            out += [(q, c("E", k, "wire", "T1", L, "none", "gflite31", seed), main) for k in (3, 8)]
        elif part == "P5":
            out += [(q, c("D", 0, None, None, L, "none", "gflite31", seed, h, n), main)
                    for h in HEDGES for n in N_AGREE]
        elif part == "P6":
            out += [(q, c("G", k, None, t, L, dfn, "gflite31", seed), held)
                    for t, k in (("T3", 3), ("T3", 8), ("T0", 8), ("T1", 8))
                    for dfn in ("none", "pagevote", "guard")]
        else:
            raise ValueError(f"unknown free part {part!r}; expected one of {FREE_PARTS}")
    return out


def _so_map(base: list[Question], test: list[Question], seed: int, notes: list[str]) -> dict:
    """base qid -> single-origin question; voids borrow an unused non-void test question's -so."""
    so_all = {q.qid.removesuffix("-so"): q for q in load_q("single_origin") if q.split == "test"}
    used = {q.qid for q in base}
    spare = [q for r, lst in regime_order(test, seed).items() if r != "void" for q in lst]
    spare = [q for q in sorted(spare, key=lambda q: q.qid) if q.qid not in used and q.qid in so_all]
    random.Random(f"{seed}:so-sub").shuffle(spare)
    out, subs = {}, []
    for q in base:
        if q.qid in so_all:
            out[q.qid] = so_all[q.qid]
        else:
            sub = spare.pop(0)
            out[q.qid] = so_all[sub.qid]
            subs.append(f"{q.qid}->{so_all[sub.qid].qid}")
    if subs:
        notes.append(f"P2 single_origin substitutions: {len(subs)} (no -so variant): {', '.join(subs)}")
    return out


def _part_base(part: str, picks: dict) -> tuple[list[Question], list[Question]]:
    """(base questions, reserve pool of the same population) for a part."""
    if part == "P1":
        return picks["q60"], picks["test"]
    if part in ("P2", "P6"):
        return picks["q40"], picks["test"]
    if part == "P3":
        return picks["q20"], picks["test"]
    if part == "P5":
        hedge = [q for q in load_q("hedge150") if q.split == "test"]
        return picks["hedge40"], hedge
    if part == "P4":
        en = {q.qid: q for q in picks["test"]}
        missing = [q.qid for q in picks["ur30"] if q.qid.removesuffix("-ur") not in en]
        if missing:
            raise AssertionError(f"P4: Urdu qids without a TEST English counterpart: {missing}")
        return picks["ur30"], _test_only(load_q("urdu60"), "urdu60")
    raise ValueError(f"unknown free part {part!r}; expected one of {FREE_PARTS}")


def build_free(part: str, seed: int = 0, engines: dict | None = None,
               check_pools: bool = False) -> tuple[list[Run], list[str]]:
    """Runs of one free-tier part. With ``check_pools``, questions whose pools are rejected are
    replaced by the next unused question of the same regime (counted in the notes)."""
    if part not in FREE_PARTS:
        raise ValueError(f"unknown free part {part!r}; expected one of {FREE_PARTS}")
    notes: list[str] = []
    picks = _free_questions(seed)
    base, population = _part_base(part, picks)
    if part == "P4":  # Urdu Q followed by their English counterparts
        en = {q.qid: q for q in picks["test"]}
    extra = {"so": _so_map(base, picks["test"], seed, notes)} if part == "P2" else {}

    def items_for(q):
        if part == "P4":
            return _free_items(part, [q, en[q.qid.removesuffix("-ur")]], extra, seed)
        return _free_items(part, [q], extra, seed)

    chosen = list(base)
    if check_pools:
        from planted.engine import MockEngine, PoolError

        engines = {} if engines is None else engines
        reserve = {r: [q for q in lst if q.qid not in {b.qid for b in base}]
                   for r, lst in regime_order(population, seed).items()}

        def rejected(q) -> str | None:
            for qq, cond, bank in items_for(q):
                eng = engines.get(bank) or engines.setdefault(bank, MockEngine.from_bank(bank, []))
                try:
                    eng.build_pool(qq, cond)
                except PoolError as e:
                    return f"{qq.qid} k={cond.k} {cond.tier}/{cond.label}: {e}"
            return None

        subs = Counter()
        for i, q in enumerate(chosen):
            why = rejected(q)
            while why is not None:
                pool = reserve.get(q.regime, [])
                if not pool:
                    raise AssertionError(f"{part}: no reserve {q.regime} question to replace {q.qid} ({why})")
                new = pool.pop(0)
                notes.append(f"{part} substitution: {q.qid} -> {new.qid} ({why})")
                subs[q.regime] += 1
                q = chosen[i] = new
                if part == "P2":
                    extra["so"].update(_so_map([new], picks["test"], seed, notes))
                why = rejected(q)
        notes.append(f"{part} pool substitutions: {sum(subs.values())}"
                     + (f" ({dict(subs)})" if subs else ""))

    runs = [Run(f"free-{part}", qq, cond, FREE_STYLE, bank)
            for q in chosen for qq, cond, bank in items_for(q)]
    _test_only([r.question for r in runs], f"free {part}")
    return runs, notes
