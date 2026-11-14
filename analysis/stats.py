# OWNER: C (written by B after C became unavailable; see PREREG.md §8) — see PLAN.md §2
"""Statistics (PREREG.md §5): Wilson CIs, question-clustered logit, bootstrap k50, bootstrap differences,
TOST equivalence, Holm adjustment.

Bootstraps resample QUESTIONS with replacement (2,000 resamples, seed 0 by default). They are vectorised:
every statistic here is a function of per-question counts, so a resample is a matrix of question weights
(W, n_boot x n_questions) applied to those counts. Groups sharing questions (e.g. defences on the same
questions) are resampled jointly; groups with disjoint question sets (e.g. void vs known) are resampled
within each group."""

from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
from scipy.stats import norm

N_BOOT = 2000
K_MAX = 10


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (math.nan, math.nan)
    z = norm.ppf(1 - alpha / 2)
    p = successes / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (0.0 if successes == 0 else max(0.0, c - h), 1.0 if successes == n else min(1.0, c + h))


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values (monotone, capped at 1)."""
    items = sorted((p, k) for k, p in pvalues.items() if p is not None and not math.isnan(p))
    m = len(items)
    out, running = {}, 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    for k in pvalues:
        out.setdefault(k, math.nan)
    return out


def clustered_logit(df: pd.DataFrame, formula: str, cluster: str = "qid"):
    """Binomial GLM with cluster-robust (by question) standard errors. Returns a statsmodels result."""
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    data = df.dropna(subset=[cluster]).copy()
    groups = pd.factorize(data[cluster])[0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = smf.glm(formula, data=data, family=sm.families.Binomial())
        return model.fit(cov_type="cluster", cov_kwds={"groups": groups})


def ci(samples: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    s = np.asarray(samples, float)
    s = s[~np.isnan(s)]
    if len(s) == 0:
        return (math.nan, math.nan)
    return (float(np.quantile(s, alpha / 2)), float(np.quantile(s, 1 - alpha / 2)))


def p_one_sided(samples: np.ndarray, null: float, greater: bool) -> float:
    """Bootstrap p-value for 'estimate > null' (greater=True) or 'estimate < null'."""
    s = np.asarray(samples, float)
    s = s[~np.isnan(s)]
    if len(s) == 0:
        return math.nan
    frac = np.mean(s <= null) if greater else np.mean(s >= null)
    return float(min(1.0, max(frac, 1.0 / (len(s) + 1))))


# ---------------------------------------------------------------------------- resampling weights
def _weights(n_q: int, n_boot: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_q, np.full(n_q, 1.0 / n_q), size=n_boot).astype(float)


def _per_question(df: pd.DataFrame, qids: np.ndarray, mask: pd.Series, y: str, cluster: str):
    g = df[mask].groupby(cluster)[y].agg(["sum", "count"]).reindex(qids, fill_value=0)
    return g["sum"].to_numpy(float), g["count"].to_numpy(float)


def boot_means(df: pd.DataFrame, group_col: str, groups: list, y: str, cluster: str = "qid",
               n_boot: int = N_BOOT, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Point means of y per group and their joint question-level bootstrap (n_boot x len(groups))."""
    qids = np.array(sorted(df[cluster].unique()))
    W = _weights(len(qids), n_boot, seed)
    points, boots = [], []
    for gname in groups:
        s, c = _per_question(df, qids, df[group_col] == gname, y, cluster)
        points.append(s.sum() / c.sum() if c.sum() else math.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            boots.append((W @ s) / (W @ c))
    return np.array(points), np.column_stack(boots)


def diff_boot(df, group_col, a, b, y, n_boot=N_BOOT, seed=0):
    pts, bs = boot_means(df, group_col, [a, b], y, n_boot=n_boot, seed=seed)
    return pts[0] - pts[1], bs[:, 0] - bs[:, 1]


def diff_ci(df: pd.DataFrame, group_col: str, a, b, y: str, n_boot: int = N_BOOT, seed: int = 0,
            alpha: float = 0.05) -> tuple[float, float, float]:
    """mean(y | a) - mean(y | b) with a question-level bootstrap CI."""
    d, bs = diff_boot(df, group_col, a, b, y, n_boot, seed)
    return d, *ci(bs, alpha)


def reduction_ci(df, group_col, base, treat, y="flip", n_boot=N_BOOT, seed=0):
    """Relative reduction (mean_base - mean_treat) / mean_base: (estimate, lo, hi, p[reduction > 0])."""
    pts, bs = boot_means(df, group_col, [base, treat], y, n_boot=n_boot, seed=seed)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (bs[:, 0] - bs[:, 1]) / bs[:, 0]
    est = (pts[0] - pts[1]) / pts[0] if pts[0] > 0 else math.nan
    return est, *ci(r), p_one_sided(r, 0.0, True)


def tost(df: pd.DataFrame, group_col: str, a, b, y: str, margin: float, n_boot: int = N_BOOT,
         seed: int = 0) -> dict:
    """Equivalence within +/- margin: passes if the 90% bootstrap CI lies inside the margin (TOST)."""
    d, bs = diff_boot(df, group_col, a, b, y, n_boot, seed)
    lo, hi = ci(bs, 0.10)
    p = max(p_one_sided(bs, -margin, True), p_one_sided(bs, margin, False))
    return {"diff": d, "ci90": (lo, hi), "margin": margin, "equivalent": bool(-margin < lo and hi < margin), "p": p}


# ---------------------------------------------------------------------------- k50 (dose at which flip rate = 0.5)
def _dose_matrix(df: pd.DataFrame, qids: np.ndarray, ks: np.ndarray, flip_col: str, k_col: str, cluster: str):
    piv_f = df.pivot_table(index=cluster, columns=k_col, values=flip_col, aggfunc="sum").reindex(index=qids, columns=ks)
    piv_n = df.pivot_table(index=cluster, columns=k_col, values=flip_col, aggfunc="count").reindex(index=qids, columns=ks)
    return piv_f.fillna(0).to_numpy(float), piv_n.fillna(0).to_numpy(float)


def _fit_k50_agg(ks: np.ndarray, F: np.ndarray, N: np.ndarray) -> np.ndarray:
    """Vectorised binomial logistic fit flip ~ k on aggregated rows; returns k50 per row of F/N.
    inf = never reaches 0.5 within K_MAX (or no positive slope); 0 = above 0.5 already at k = 0."""
    B = F.shape[0]
    b = np.tile(np.array([-1.0, 0.3]), (B, 1))
    X = np.column_stack([np.ones_like(ks), ks]).astype(float)  # D x 2
    for _ in range(50):
        z = b @ X.T                                   # B x D
        p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        w = N * p * (1 - p) + 1e-9
        g = (F - N * p) @ X                           # B x 2 gradient
        H = np.einsum("bd,di,dj->bij", w, X, X) + 1e-6 * np.eye(2)
        step = np.linalg.solve(H, g[..., None])[..., 0]
        b = b + np.clip(step, -5, 5)
    b0, b1 = b[:, 0], b[:, 1]
    with np.errstate(divide="ignore", invalid="ignore"):
        k50 = -b0 / b1
    rate = F.sum(1) / np.maximum(N.sum(1), 1)
    out = np.where(b1 <= 1e-6, np.where(rate > 0.5, 0.0, np.inf), k50)
    out = np.where(np.isfinite(out) & (out > K_MAX), np.inf, out)
    return np.where(np.isfinite(out), np.maximum(out, 0.0), out)


def _k50_parts(df, flip_col="flip", k_col="k", cluster="qid"):
    d = df[df[k_col] > 0]
    qids = np.array(sorted(d[cluster].unique()))
    ks = np.array(sorted(d[k_col].unique()), float)
    F, N = _dose_matrix(d, qids, ks, flip_col, k_col, cluster)
    return qids, ks, F, N


def k50(df: pd.DataFrame, flip_col: str = "flip", k_col: str = "k", cluster: str = "qid") -> float:
    """Point estimate of k50 from runs with k > 0 (PREREG.md §5)."""
    qids, ks, F, N = _k50_parts(df, flip_col, k_col, cluster)
    if len(ks) < 2:
        return math.nan
    return float(_fit_k50_agg(ks, F.sum(0, keepdims=True), N.sum(0, keepdims=True))[0])


def _boot_k50(df, n_boot, seed, W=None, qids_order=None):
    qids, ks, F, N = _k50_parts(df)
    if qids_order is not None:  # align to a shared question order for joint resampling
        Fd = pd.DataFrame(F, index=qids).reindex(qids_order, fill_value=0).to_numpy()
        Nd = pd.DataFrame(N, index=qids).reindex(qids_order, fill_value=0).to_numpy()
        F, N = Fd, Nd
    if W is None:
        W = _weights(F.shape[0], n_boot, seed)
    return _fit_k50_agg(ks, W @ F, W @ N)


def k50_ci(df: pd.DataFrame, n_boot: int = N_BOOT, seed: int = 0) -> tuple[float, float, float]:
    """(k50, lo, hi). Infinite values mean 'never reaches 0.5 within k <= 10' (reported as '> 10')."""
    point = k50(df)
    boots = _boot_k50(df, n_boot, seed)
    boots = np.where(np.isinf(boots), K_MAX + 1, boots)  # a bound, so quantiles stay defined
    return point, *ci(boots)


def k50_ratio_boot(df_a: pd.DataFrame, df_b: pd.DataFrame, n_boot: int = N_BOOT, seed: int = 0):
    """k50(a)/k50(b): point and bootstrap samples. Shared questions are resampled jointly; disjoint
    question sets are resampled within each group."""
    qa, qb = set(df_a["qid"]), set(df_b["qid"])
    if qa == qb:
        order = np.array(sorted(qa))
        W = _weights(len(order), n_boot, seed)
        ba = _boot_k50(df_a, n_boot, seed, W, order)
        bb = _boot_k50(df_b, n_boot, seed, W, order)
    else:
        ba = _boot_k50(df_a, n_boot, seed)
        bb = _boot_k50(df_b, n_boot, seed + 1)
    cap = lambda x: np.minimum(np.where(np.isinf(x), K_MAX + 1, x), K_MAX + 1)  # noqa: E731
    with np.errstate(divide="ignore", invalid="ignore"):
        r = cap(ba) / cap(bb)
    pa, pb = k50(df_a), k50(df_b)
    pa, pb = min(pa, K_MAX + 1), min(pb, K_MAX + 1)
    return (pa / pb if pb and pb > 0 else math.nan), r


def ratio_ci(df_a: pd.DataFrame, df_b: pd.DataFrame, n_boot: int = N_BOOT, seed: int = 0) -> tuple[float, float, float]:
    point, r = k50_ratio_boot(df_a, df_b, n_boot, seed)
    return point, *ci(r)


def rate_table(df: pd.DataFrame, by: list[str], y: str = "flip") -> pd.DataFrame:
    """Rate of y per group with Wilson 95% CIs."""
    rows = []
    for key, g in df.groupby(by, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        k, n = int(g[y].sum()), len(g)
        lo, hi = wilson_ci(k, n)
        rows.append({**dict(zip(by, key)), "n": n, y: k, "rate": k / n if n else math.nan, "lo": lo, "hi": hi})
    return pd.DataFrame(rows)
