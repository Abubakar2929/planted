# OWNER: C (written by B after C became unavailable; see PREREG.md §8) — see PLAN.md §2
"""Figures: hero dose curves (with/without Guard), bench dose curves by label, attacker tiers, cost panel,
hedge retention and English vs Urdu. Each figure is drawn only if its data exist in the logs.
Colours follow the entity, never its rank (fixed mapping below); whiskers are Wilson 95% intervals."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from analysis import stats as S  # noqa: E402

INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
DEFENCE_COLOR = {"none": "#8a8984", "prompt": "#e87ba4", "pagevote": "#eb6834", "guard_noprov": "#eda100", "guard": "#2a78d6"}
DEFENCE_NAME = {"none": "no defence", "prompt": "reliability prompt", "pagevote": "page vote",
                "guard_noprov": "Guard - provenance", "guard": "Guard"}
LABEL_COLOR = {"wire": "#2a78d6", "propaganda": "#eb6834", "blog": "#1baf7a"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
plt.rcParams.update({"font.size": 7, "axes.titlesize": 8, "axes.labelsize": 7, "legend.fontsize": 6.5,
                     "xtick.labelsize": 7, "ytick.labelsize": 7, "figure.dpi": 100})


def _style(ax, ylabel=None, ylim=(0, 1.02)):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#b8b7b2")
    ax.tick_params(colors=INK2, length=2)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    if ylim:
        ax.set_ylim(*ylim)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    if ylabel:
        ax.set_ylabel(ylabel, color=INK)


def _curve(ax, g: pd.DataFrame, color: str, label: str, y="flip", x="k"):
    pts = []
    for k, gg in g.groupby(x):
        s, n = int(gg[y].sum()), len(gg)
        lo, hi = S.wilson_ci(s, n)
        pts.append((k, s / n, lo, hi))
    if not pts:
        return
    pts.sort()
    ks, ps, los, his = map(np.array, zip(*pts))
    ax.plot(ks, ps, color=color, linewidth=2, marker="o", markersize=3.5, label=label)
    ax.fill_between(ks, los, his, color=color, alpha=0.12, linewidth=0)


def _save(fig, out: Path, name: str, made: list) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out / name, dpi=300, facecolor=SURFACE)
    plt.close(fig)
    made.append(name)


def hero_figure(df: pd.DataFrame, out: Path, made: list | None = None) -> None:
    """Flip rate vs planted pages, one panel per Guard model: lines per defence (held-out T1 pages)."""
    made = made if made is not None else []
    g = df[(df["arm"] == "G") & (df["regime"] == "known") & ((df["tier"] == "T1") | (df["k"] == 0))]
    if g.empty or g["k"].nunique() < 2:
        return
    models = sorted(m for m in g["model"].unique() if g.loc[g["model"] == m, "k"].nunique() >= 2)  # a curve needs 2 doses
    if not models:
        return
    fig, axes = plt.subplots(1, len(models), figsize=(3.4 * len(models), 2.5), squeeze=False, sharey=True)
    for ax, m in zip(axes[0], models):
        for d in ("none", "pagevote", "guard_noprov", "guard"):
            _curve(ax, g[(g["model"] == m) & (g["defense"] == d)], DEFENCE_COLOR[d], DEFENCE_NAME[d])
        _style(ax, "flip rate" if ax is axes[0][0] else None)
        ax.set_xlabel("planted pages out of 10 (k)")
        ax.set_title(m, color=INK)
    axes[0][0].legend(frameon=False, loc="upper left")
    fig.suptitle("Flip rate by defence, known facts, held-out T1 attack pages (bands: Wilson 95% CI)",
                 fontsize=7.5, x=0.01, ha="left", color=INK)
    _save(fig, out, "fig1_hero.png", made)


def bench_figure(df: pd.DataFrame, out: Path, made: list) -> None:
    g = df[df["arm"].isin(["A", "B"])]
    if g.empty:
        return
    models = sorted(g["model"].unique())
    fig, axes = plt.subplots(1, len(models), figsize=(3.0 * len(models), 2.4), squeeze=False, sharey=True)
    for ax, m in zip(axes[0], models):
        gm = g[g["model"] == m]
        for lab in ("wire", "propaganda", "blog"):
            _curve(ax, gm[(gm["label"] == lab) & (gm["regime"] == "known")], LABEL_COLOR[lab], f"{lab} (known facts)")
        _curve(ax, gm[gm["regime"] == "void"], "#6250d6", "data voids (all labels)")
        _style(ax, "flip rate" if ax is axes[0][0] else None)
        ax.set_xlabel("planted pages out of 10 (k)")
        ax.set_title(m, color=INK)
    axes[0][0].legend(frameon=False, loc="upper left")
    _save(fig, out, "fig_bench_dose.png", made)


def tier_figure(df: pd.DataFrame, out: Path, made: list) -> None:
    g = df[df["arm"].isin(["G", "T4"]) & (df["regime"] == "known") & (df["k"] == 8) & df["defense"].isin(["none", "guard"])]
    tiers = [t for t in ("T0", "T1", "T3", "T4") if t in set(g["tier"])]
    if len(tiers) < 1:
        return
    models = sorted(g["model"].unique())
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    w = 0.8 / max(1, len(models))
    for i, m in enumerate(models):
        xs, ys = [], []
        for j, t in enumerate(tiers):
            gg = g[(g["model"] == m) & (g["tier"] == t)]
            b, tr = gg.loc[gg.defense == "none", "flip"].mean(), gg.loc[gg.defense == "guard", "flip"].mean()
            if b and b > 0 and not math.isnan(tr):
                xs.append(j - 0.4 + w * (i + 0.5))
                ys.append((b - tr) / b)
        ax.bar(xs, ys, width=w * 0.9, color=SERIES[i % len(SERIES)], label=m)
    ax.axhline(0.5, color=INK2, linewidth=0.8, linestyle="--")
    ax.text(len(tiers) - 0.55, 0.52, "G1 target", fontsize=6, color=INK2)
    ax.set_xticks(range(len(tiers)))
    ax.set_xticklabels(tiers)
    _style(ax, "relative flip reduction (k = 8)", ylim=(min(0, ax.get_ylim()[0]), 1.02))
    ax.legend(frameon=False)
    _save(fig, out, "fig2_tiers.png", made)


def cost_figure(df: pd.DataFrame, out: Path, made: list) -> None:
    g = df[(df["arm"] == "G") & (df["k"] == 0) & df["defense"].isin(["none", "guard"])]
    panels = [("known", "correct", "clean accuracy (k = 0)"), ("syndication", "correct", "benign syndication accuracy"),
              ("single_origin", "correct", "single-origin: confident correct")]
    panels = [p for p in panels if not g[g["regime"] == p[0]].empty]
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=(2.3 * len(panels), 2.3), squeeze=False, sharey=True)
    for ax, (reg, y, title) in zip(axes[0], panels):
        for i, d in enumerate(("none", "guard")):
            gg = g[(g["regime"] == reg) & (g["defense"] == d)]
            vals = gg[y] * (1 - gg["hedged_ans"]) if reg == "single_origin" else gg[y]
            s, n = int(vals.sum()), len(vals)
            if n == 0:
                continue
            lo, hi = S.wilson_ci(s, n)
            ax.bar(i, s / n, color=DEFENCE_COLOR[d], width=0.6)
            ax.errorbar(i, s / n, yerr=[[s / n - lo], [hi - s / n]], fmt="none", ecolor=INK, elinewidth=0.8, capsize=2)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["no defence", "Guard"])
        ax.set_title(title, color=INK)
        _style(ax)
    _save(fig, out, "fig_cost.png", made)


def hedge_figure(df: pd.DataFrame, out: Path, made: list) -> None:
    from analysis.analyze import _retained

    g = df[(df["arm"] == "D") & df["source_hedge"].isin(["may", "preliminary", "disagree"])]
    if g.empty:
        return
    g = g.assign(ret=g.apply(_retained, axis=1))
    levels = ["may", "preliminary", "disagree"]
    fig, ax = plt.subplots(figsize=(3.2, 2.3))
    for i, n in enumerate(sorted(g["n_agree"].dropna().unique())):
        xs, ys, lo_, hi_ = [], [], [], []
        for j, lv in enumerate(levels):
            gg = g[(g["source_hedge"] == lv) & (g["n_agree"] == n)]
            if gg.empty:
                continue
            s, m = int(gg["ret"].sum()), len(gg)
            lo, hi = S.wilson_ci(s, m)
            xs.append(j - 0.2 + 0.4 * i)
            ys.append(s / m)
            lo_.append(s / m - lo)
            hi_.append(hi - s / m)
        ax.bar(xs, ys, width=0.36, color=SERIES[i], label=f"{int(n)} agreeing source{'s' if n > 1 else ''}")
        ax.errorbar(xs, ys, yerr=[lo_, hi_], fmt="none", ecolor=INK, elinewidth=0.8, capsize=2)
    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels(levels)
    _style(ax, "hedge kept in the answer")
    ax.legend(frameon=False)
    _save(fig, out, "fig3_hedges.png", made)


def urdu_figure(df: pd.DataFrame, out: Path, made: list) -> None:
    g = df[df["arm"] == "E"]
    if g["lang"].nunique() < 2:
        return
    fig, ax = plt.subplots(figsize=(3.2, 2.3))
    for i, lang in enumerate(("en", "ur")):
        _curve(ax, g[g["lang"] == lang], SERIES[i], {"en": "English", "ur": "Urdu"}[lang])
    _style(ax, "flip rate")
    ax.set_xlabel("planted pages out of 10 (k)")
    ax.legend(frameon=False)
    _save(fig, out, "fig_urdu.png", made)


def make_all(df: pd.DataFrame, out: Path) -> list[str]:
    made: list[str] = []
    for f in (hero_figure, bench_figure, tier_figure, cost_figure, hedge_figure, urdu_figure):
        f(df, out, made)
    return made
