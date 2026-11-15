# OWNER: C — see PLAN.md §2 (written by A; A never opened data/generator or data/heldout)
"""guard(query, results, lang) public API; equals apply_defense("guard", ...).

Pipeline (plan-v2.2 §Architecture): extract one answer per page (planted.guard.extract; method from
PLANTED_EXTRACT, default rules) -> page graph and origins (cluster.py) -> vote by independent origins
(vote.py) -> reweight, never delete -> data-void / contested gate -> hedge floor (hedge.py).
Thresholds come from planted.guard.config (tuned on dev20 only, frozen before test/held-out).
Only visible result keys are read; hidden Page fields are never read or added.
"""

from __future__ import annotations

import os

from contracts.schemas import GuardResult
from planted.guard import config
from planted.guard.cluster import PairFeatures, graph_from, pair_features
from planted.guard.hedge import hedge_floor as _floor
from planted.guard.vote import Tally, contested, tally, tied

DATA_VOID_WARNING = "DATA_VOID: fewer than 2 independent origins support any answer"
GATE_FLOOR = "may"
EMBED_ENV = "PLANTED_GUARD_EMBED"  # "0" disables embedding edges (runtime measurements, offline use)

NOTE = {
    "en": {
        "head": "Independent-source check: ",
        "first": "'{a}' is supported by {p} pages from {o} independent origin(s)",
        "other": "'{a}' by {p} pages from {o} origin(s)",
        "tail": ". Copies of the same story count once. Prefer answers backed by more independent origins.",
        "none": "Independent-source check: no page states an answer to the question.",
    },
    "ur": {
        "head": "آزاد ذرائع کی جانچ: ",
        "first": "'{a}' کی تائید {p} صفحات کرتے ہیں جو {o} آزاد ماخذ سے ہیں",
        "other": "'{a}' کی {p} صفحات، {o} ماخذ سے",
        "tail": "۔ ایک ہی خبر کی نقول ایک بار گنی جاتی ہیں۔ زیادہ آزاد ماخذ والے جواب کو ترجیح دیں۔",
        "none": "آزاد ذرائع کی جانچ: کوئی صفحہ اس سوال کا جواب نہیں دیتا۔",
    },
}


class GuardOutput(GuardResult):
    """GuardResult (= DefenseOut fields) plus the origin tally and the graph, for users and evaluation."""

    origins: dict[str, dict] = {}       # answer -> {"pages": int, "origins": int}
    top_answer: str | None = None       # as written on its first page
    top_answer_norm: str | None = None
    edges: list[dict] = []              # {"i", "j", "signals": [...], "jaccard"?, "cosine"?}
    config_hash: str = ""


def params(overrides: dict | None = None) -> dict:
    p = {"tau_content": config.TAU_CONTENT, "tau_embed": config.TAU_EMBED,
         "gate_margin": config.GATE_MARGIN, "min_origins": config.MIN_ORIGINS,
         "num_perm": config.NUM_PERM, "seed": config.MINHASH_SEED, "tau_para": config.TAU_PARA}
    p.update(overrides or {})
    return p


def system_note(tallies: list[Tally], lang: str) -> str:
    t = NOTE["ur" if lang == "ur" else "en"]
    if not tallies:
        return t["none"]
    parts = [t["first"].format(a=tallies[0].display, p=tallies[0].n_pages, o=tallies[0].n_origins)]
    if len(tallies) > 1:
        parts.append(t["other"].format(a=tallies[1].display, p=tallies[1].n_pages, o=tallies[1].n_origins))
    sep = "؛ " if lang == "ur" else "; "
    return t["head"] + sep.join(parts) + t["tail"]


def _note(i: int, cid: int, members: list[int], ans: str | None, t: Tally | None) -> str:
    if members[0] != i:
        return f"Same origin as result #{members[0] + 1}; counted once."
    size = f"origin of {len(members)} pages" if len(members) > 1 else "independent origin"
    if ans is None or t is None:
        return f"{size.capitalize()}; states no answer."
    return f"{size.capitalize()}; says '{ans}', backed by {t.n_origins} independent origin(s)."


def guard(query: str, results: list[dict], lang: str = "en", use_provenance: bool = True, *,
          use_embeddings: bool | None = None, overrides: dict | None = None,
          extract_method: str | None = None) -> GuardOutput:
    """Count independent origins, not pages. Never deletes a result."""
    from planted.guard.extract import extract_answers

    p = params(overrides)
    if use_embeddings is None:
        use_embeddings = os.environ.get(EMBED_ENV, "1").strip() != "0"
    if extract_method is None:
        from planted.baselines import extract_method as _em

        extract_method = _em()
    if not results:
        return GuardOutput(results=[], system_note=system_note([], lang), warnings=[DATA_VOID_WARNING],
                           hedge_floor=GATE_FLOOR, config_hash=config.CONFIG_HASH)

    ext = extract_answers(query, results, lang, method=extract_method)
    feats = pair_features(results, [e["answer"] for e in ext], lang, use_provenance=use_provenance,
                          use_embeddings=use_embeddings, num_perm=p["num_perm"], seed=p["seed"],
                          para=p["tau_para"] is not None)
    return assemble(results, lang, ext, feats, p, use_provenance)


def assemble(results: list[dict], lang: str, ext: list[dict], feats: PairFeatures, p: dict,
             use_provenance: bool = True) -> GuardOutput:
    """Thresholds -> origins -> vote -> reorder/annotate -> gate -> hedge floor. Split from guard() so
    the dev tuning script can reuse one extraction and one set of pair features per pool."""
    raw = [e["answer"] for e in ext]
    norm = [e["answer_norm"] for e in ext]
    g = graph_from(feats, tau_content=p["tau_content"], tau_embed=p["tau_embed"],
                   use_provenance=use_provenance, tau_para=p.get("tau_para"))
    cids = g.cluster_ids
    tallies = tally(norm, raw, cids)
    by_answer = {t.answer: t for t in tallies}
    total_origins = sum(t.n_origins for t in tallies)
    top = tallies[0] if tallies else None

    members: dict[int, list[int]] = {}
    for i, c in enumerate(cids):
        members.setdefault(c, []).append(i)

    # Reweight, never delete: one representative per origin backing the top answer, then the first
    # page of every other origin by its answer's origin support, then duplicates in input order.
    first_reps: list[int] = []
    if top is not None:
        for c in top.origins:
            first_reps.append(next(i for i in members[c] if norm[i] == top.answer))
    rest_reps = [m[0] for c, m in members.items() if m[0] not in first_reps
                 and not (top is not None and c in top.origins)]
    rest_reps.sort(key=lambda i: (-(by_answer[norm[i]].n_origins if norm[i] in by_answer else 0), i))
    placed = set(first_reps) | set(rest_reps)
    order = first_reps + rest_reps + [i for i in range(len(results)) if i not in placed]
    assert sorted(order) == list(range(len(results)))  # nothing deleted, nothing duplicated

    out = []
    for i in order:
        r = dict(results[i])
        t = by_answer.get(norm[i]) if norm[i] is not None else None
        share = (t.n_origins / total_origins) if (t and total_origins) else 0.0
        r["extracted_answer"] = raw[i]
        r["hedge_level"] = ext[i]["hedge_level"]
        r["cluster_id"] = cids[i]
        r["guard_score"] = round(share / len(members[cids[i]]), 4)
        r["note"] = _note(i, cids[i], members[cids[i]], raw[i], t)
        out.append(r)

    warnings = list(g.warnings)
    gate = False
    if top is None or top.n_origins < p["min_origins"]:
        warnings.append(DATA_VOID_WARNING)
        gate = True
    if tied(tallies):  # rank breaks the tie; always flagged and hedged
        warnings.append("CONTESTED: the top two answers have the same number of independent origins")
        gate = True
    elif contested(tallies, p["gate_margin"]):
        warnings.append(f"CONTESTED: the top two answers are within {p['gate_margin']} independent "
                        f"origin(s) of each other")
        gate = True
    support_levels = [ext[i]["hedge_level"] for i in (top.pages if top else [])]
    floor = _floor(support_levels, GATE_FLOOR if gate else None)

    return GuardOutput(
        results=out, system_note=system_note(tallies, lang), warnings=warnings, hedge_floor=floor,
        origins={t.display: {"pages": t.n_pages, "origins": t.n_origins} for t in tallies},
        top_answer=top.display if top else None, top_answer_norm=top.answer if top else None,
        edges=g.edges, config_hash=config.CONFIG_HASH,
    )


def guard_noprov(query: str, results: list[dict], lang: str = "en", **kw) -> GuardOutput:
    """Ablation: content MinHash edges only (no provenance, no embedding edges)."""
    return guard(query, results, lang, use_provenance=False, **kw)
