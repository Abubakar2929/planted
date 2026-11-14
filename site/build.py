# OWNER: C (written by B after C became unavailable; see PREREG.md §8) — see PLAN.md §2
"""Build the static scorecard and episode viewer (GitHub Pages; English / Urdu).

    python site/build.py --results results --logs logs --out site/dist

(Run as a script: `site` is also the name of a Python standard-library module, so `-m site.build` would not work.)

Writes `index.html` (one-page scorecard for fact-checkers: no code to run) and `viewer.html` (recorded
episodes: the ten results an agent saw, its answer, and, with Guard, the origin groups). Everything is
precomputed and embedded, so the pages never call a model and never need a key. Numbers come only from
`results/summary.json` (written by `python -m analysis.analyze`); if it is missing the scorecard says the
results are pending instead of showing anything.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEMO_QIDS = ["pl-support-001", "pl-support-001-ur"]  # fictional brand used in the video

T = {
    "en": {"title": "Planted: do AI search agents count pages or sources?", "pending": "Results pending: the experiments have not been run yet.",
           "lead": "When several search results repeat a claim, AI search agents tend to believe it, even if all the pages come from one campaign. This page summarises how often that happens and how much our fix (Guard) helps.",
           "flip": "Answers flipped by planting 3 of 10 results", "k50": "Planted pages needed to flip half the answers (k50)",
           "label": "Pages needed with a wire label vs a propaganda label (k50 ratio)", "guard": "Flip rate with Guard (5 planted pages)",
           "cost": "Accuracy cost of Guard on clean results", "how": "How to read this", "method": "Method",
           "method_text": "Fictional questions and websites (no real outlets or brands). Ten search results per question; we vary how many repeat a planted answer. Every rate has a 95% confidence interval. Hypotheses and thresholds were registered before the main run.",
           "viewer": "See recorded examples", "lang": "اردو", "na": "not measured yet"},
    "ur": {"title": "پلانٹڈ: کیا اے آئی سرچ ایجنٹ صفحات گنتے ہیں یا ذرائع؟", "pending": "نتائج زیرِ التوا: تجربات ابھی نہیں کیے گئے۔",
           "lead": "جب کئی سرچ نتائج ایک ہی دعویٰ دہراتے ہیں تو اے آئی سرچ ایجنٹ اکثر اسے سچ مان لیتے ہیں، چاہے تمام صفحات ایک ہی مہم سے آئے ہوں۔ یہ صفحہ بتاتا ہے کہ ایسا کتنی بار ہوتا ہے اور ہمارا حل (گارڈ) کتنی مدد کرتا ہے۔",
           "flip": "دس میں سے تین نتائج بدلنے سے پلٹ جانے والے جوابات", "k50": "آدھے جوابات پلٹنے کے لیے درکار جعلی صفحات (k50)",
           "label": "وائر لیبل بمقابلہ پروپیگنڈا لیبل: درکار صفحات کا تناسب (k50)", "guard": "گارڈ کے ساتھ جوابات پلٹنے کی شرح (پانچ جعلی صفحات)",
           "cost": "صاف نتائج پر گارڈ کی درستی کی قیمت", "how": "اسے کیسے پڑھیں", "method": "طریقۂ کار",
           "method_text": "فرضی سوالات اور ویب سائٹس (کوئی حقیقی ادارہ یا برانڈ نہیں)۔ ہر سوال کے دس سرچ نتائج؛ ہم بدلتے ہیں کہ ان میں سے کتنے ایک جعلی جواب دہراتے ہیں۔ ہر شرح کے ساتھ 95 فیصد اعتماد کا وقفہ ہے۔ مفروضے اور حدیں مرکزی تجربے سے پہلے رجسٹر کی گئیں۔",
           "viewer": "ریکارڈ شدہ مثالیں دیکھیں", "lang": "English", "na": "ابھی ناپا نہیں گیا"},
}

CSS = """
:root{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e4e3df;--blue:#2a78d6;--orange:#eb6834;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--line:#33322f;--card:#222220;--blue:#3987e5;--orange:#d95926}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px}h1{font-size:1.6rem;line-height:1.25;margin:.2em 0 .4em}
.lead{color:var(--ink2)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:20px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.k{font-size:.85rem;color:var(--ink2)}
.v{font-size:1.9rem;font-weight:650;margin-top:4px}.ci{font-size:.8rem;color:var(--ink2)}button,a.btn{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 12px;cursor:pointer;text-decoration:none}
[dir=rtl]{font-family:"Noto Nastaliq Urdu","Jameel Noori Nastaleeq",serif;line-height:2}.res{border-top:1px solid var(--line);padding:8px 0}
.res .d{font-size:.8rem;color:var(--ink2)}.badge{display:inline-block;font-size:.75rem;border-radius:999px;padding:1px 8px;margin-inline-start:6px;border:1px solid var(--line)}
.planted{border-color:var(--orange);color:var(--orange)}.grp{display:inline-block;width:10px;height:10px;border-radius:50%;margin-inline-end:6px;vertical-align:middle}
.pending{border:1px dashed var(--ink2);border-radius:10px;padding:14px;color:var(--ink2)}footer{margin-top:28px;font-size:.8rem;color:var(--ink2)}
"""


def _num(x, pct=False):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return f"{100 * x:.0f}%" if pct else f"{x:.1f}"


def headline(results: Path) -> dict | None:
    s = results / "summary.json"
    if not s.exists():
        return None
    summary = json.loads(s.read_text(encoding="utf-8"))
    out = {"runs": summary.get("runs"), "models": summary.get("models")}
    rates_p = results / "rates.csv"
    if rates_p.exists():
        r = pd.read_csv(rates_p)
        if "regime" in r:
            r_known = r[r["regime"] == "known"]
        else:
            r_known = r
        for lang in ("en", "ur"):
            g = r_known[(r["arm"].isin(["A", "B", "E"])) & (r["k"] == 3) & (r["lang"] == lang) & (r["defense"] == "none")]
            if len(g):
                n = g["n"].sum()
                out[f"flip3_{lang}"] = float((g["flip"] * g["n"]).sum() / n)
        g = r[(r["arm"] == "G") & (r["k"] == 5) & (r["tier"] == "T1")]
        for d in ("none", "guard"):
            gg = g[g["defense"] == d]
            if len(gg):
                out[f"g5_{d}"] = float((gg["flip"] * gg["n"]).sum() / gg["n"].sum())
    k = results / "k50.csv"
    if k.exists():
        kd = pd.read_csv(k)
        known = kd[kd["regime"] == "known"]
        if len(known):
            out["k50_min"] = float(known["k50"].replace([float("inf")], float("nan")).min())
    hyp = summary.get("hypotheses", {})
    if "G3" in hyp and hyp["G3"].get("estimate") not in (None, "None"):
        out["clean_cost"] = float(hyp["G3"]["estimate"])
    if "H2" in hyp and hyp["H2"].get("estimate") not in (None, "None"):
        out["label_ratio"] = float(hyp["H2"]["estimate"])
    return out


def card(key: str, value: str | None, t: dict) -> str:
    return f'<div class="card"><div class="k">{html.escape(t[key])}</div><div class="v">{html.escape(value) if value else "—"}</div>' + (
        "" if value else f'<div class="ci">{html.escape(t["na"])}</div>') + "</div>"


def scorecard(h: dict | None) -> str:
    pages = []
    for lang in ("en", "ur"):
        t = T[lang]
        body = f'<div class="pending">{html.escape(t["pending"])}</div>' if h is None else '<div class="grid">' + "".join([
            card("flip", _num(h.get(f"flip3_{lang}"), True), t),
            card("k50", _num(h.get("k50_min")), t),
            card("label", None if h.get("label_ratio") is None else f"×{h['label_ratio']:.2f}", t),
            card("guard", _num(h.get("g5_guard"), True), t),
            card("cost", None if _num(h.get("clean_cost")) is None else f"{100 * h['clean_cost']:.1f} pts", t),
        ]) + "</div>"
        pages.append(f'''<section id="{lang}" lang="{lang}" dir="{'rtl' if lang == 'ur' else 'ltr'}" {'hidden' if lang == 'ur' else ''}>
<p><button onclick="sw('{'ur' if lang == 'en' else 'en'}')">{html.escape(t['lang'])}</button></p>
<h1>{html.escape(t['title'])}</h1><p class="lead">{html.escape(t['lead'])}</p>{body}
<h2>{html.escape(t['method'])}</h2><p>{html.escape(t['method_text'])}</p>
<p><a class="btn" href="viewer.html">{html.escape(t['viewer'])}</a></p></section>''')
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Planted scorecard</title><style>{CSS}</style></head><body><main>{''.join(pages)}
<footer>Planted · fictional data only · numbers from <code>results/summary.json</code></footer></main>
<script>function sw(l){{document.getElementById('en').hidden=l!=='en';document.getElementById('ur').hidden=l!=='ur';}}</script></body></html>'''


def episodes(logs: Path, bank_dirs: dict[str, Path], qids: list[str], limit: int = 12) -> list[dict]:
    """Recorded episodes for the demo questions, with the ten results rebuilt from the page bank."""
    from contracts.schemas import Condition, LogLine
    from data.pools import PageBank, build_pool, load_questions

    qs = {q.qid: q for f in ("test", "dev20", "urdu60", "single_origin", "syndication", "hedge150") for q in load_questions(ROOT / "data" / "questions" / f"{f}.jsonl")}
    banks = {k: PageBank.load(v) for k, v in bank_dirs.items() if (v / "pages.jsonl").exists()}
    merges = {}
    mp = logs / "guard_merges.jsonl"
    if mp.exists():
        for line in open(mp, encoding="utf-8"):
            m = json.loads(line)
            if m.get("same_cluster"):
                merges.setdefault(m["episode_id"], []).append((m["url_a"], m["url_b"]))
    out = []
    for path in sorted(logs.rglob("*.jsonl")):
        if path.name in ("guard_merges.jsonl", "realweb.jsonl"):
            continue
        for line in open(path, encoding="utf-8"):
            try:
                ll = LogLine.model_validate_json(line)
            except Exception:
                continue
            if ll.qid not in qids or ll.qid not in qs:
                continue
            bank = banks.get("heldout" if ll.arm in ("G", "T4") else "main")
            if bank is None:
                continue
            cond = Condition(**{k: getattr(ll, k) for k in Condition.model_fields})
            pool = build_pool(bank, qs[ll.qid], cond)
            groups = _groups([p.url for p in pool], merges.get(ll.episode_id, []))
            out.append({"episode": ll.episode_id, "arm": ll.arm, "k": ll.k, "defense": ll.defense, "lang": ll.lang,
                        "model": ll.model, "question": qs[ll.qid].question, "answer": ll.final_answer,
                        "outcome": ll.outcome, "results": [{"title": p.title, "domain": p.domain, "snippet": p.snippet,
                                                            "planted": p.planted, "group": groups.get(p.url)} for p in pool]})
            if len(out) >= limit:
                return out
    return out


def _groups(urls: list[str], pairs: list[tuple[str, str]]) -> dict[str, int]:
    parent = {u: u for u in urls}

    def find(u):
        while parent[u] != u:
            parent[u] = parent[parent[u]]
            u = parent[u]
        return u

    for a, b in pairs:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    roots = {}
    return {u: roots.setdefault(find(u), len(roots)) for u in urls}


def viewer(eps: list[dict]) -> str:
    data = json.dumps(eps, ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Planted episode viewer</title><style>{CSS}</style></head><body><main>
<p><a class="btn" href="index.html">&larr; scorecard</a></p><h1>Recorded episodes</h1>
<p class="lead">Each episode is a real logged run: the ten results the agent saw, and its answer. Planted results are marked
after the fact (the agent never saw the marks). With Guard, results that share an origin share a colour.</p>
<p><select id="sel"></select> <label><input type="checkbox" id="reveal" checked> mark planted results</label></p>
<div id="ep"></div><footer>Fictional data only.</footer></main>
<script>
const E={data};const C=["#2a78d6","#eb6834","#1baf7a","#eda100","#e87ba4","#6250d6","#008300","#e34948","#52514e","#8a8984"];
const sel=document.getElementById('sel'),ep=document.getElementById('ep'),rv=document.getElementById('reveal');
function esc(s){{return String(s??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]))}}
E.forEach((e,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=`${{e.defense}} · k=${{e.k}} · ${{e.lang}} · ${{e.model}}`;sel.appendChild(o)}});
function show(){{const e=E[sel.value];if(!e){{ep.innerHTML='<div class="pending">No recorded episodes for the demo questions yet.</div>';return}}
const groups=new Set(e.results.map(r=>r.group).filter(g=>g!=null));
let h=`<div dir="${{e.lang==='ur'?'rtl':'ltr'}}"><h2>${{esc(e.question)}}</h2>`;
if(e.defense==='guard'&&groups.size)h+=`<p><b>independent origins: ${{groups.size}}</b> (not ${{e.results.length}})</p>`;
e.results.forEach(r=>{{const dot=(e.defense==='guard'&&r.group!=null)?`<span class="grp" style="background:${{C[r.group%C.length]}}"></span>`:'';
h+=`<div class="res">${{dot}}<b>${{esc(r.title)}}</b>${{rv.checked&&r.planted?'<span class="badge planted">planted</span>':''}}<div class="d">${{esc(r.domain)}}</div><div>${{esc(r.snippet)}}</div></div>`}});
h+=`<div class="card" style="margin-top:12px"><div class="k">agent's answer (${{esc(e.outcome)}})</div><div>${{esc(e.answer)}}</div></div></div>`;ep.innerHTML=h}}
sel.onchange=show;rv.onchange=show;show();
</script></body></html>'''


def build(results: Path, logs: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    h = headline(results)
    (out / "index.html").write_text(scorecard(h), encoding="utf-8")
    eps = episodes(logs, {"main": ROOT / "data" / "pages" / "main", "heldout": ROOT / "data" / "heldout" / "pages"},
                   DEMO_QIDS) if logs.exists() else []
    (out / "viewer.html").write_text(viewer(eps), encoding="utf-8")
    return {"headline": h, "episodes": len(eps)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", type=Path, default=ROOT / "results")
    ap.add_argument("--logs", type=Path, default=ROOT / "logs")
    ap.add_argument("--out", type=Path, default=ROOT / "site" / "dist")
    a = ap.parse_args(argv)
    print(json.dumps(build(a.results, a.logs, a.out), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
