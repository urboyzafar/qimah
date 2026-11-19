"""
Qimah (قيمة) — UAE real-time skill pricing & compensation terminal.

Run:  streamlit run app.py
Every figure on screen is computed by engine.py from the files in ./data,
which are re-read on every interaction.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import json
import os
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine

st.set_page_config(page_title="Qimah (قيمة) · UAE Skill Pricing Terminal", page_icon="◆",
                   layout="wide", initial_sidebar_state="collapsed")

# ------------------------------------------------------------------------------------
# Design tokens
# ------------------------------------------------------------------------------------
BG, CARD, BORDER = "#0B1612", "#12231D", "#1E3A30"
JADE, JADE2 = "#10B981", "#1DB978"
AMBER, AMBER2 = "#EAB308", "#F59E0B"
TEXT, MUTED = "#F2F5F3", "#94A89E"
MONO = "'JetBrains Mono','SF Mono',ui-monospace,Menlo,Consolas,monospace"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
:root {{ --bg:{BG}; --card:{CARD}; --border:{BORDER}; --jade:{JADE}; --jade2:{JADE2};
        --amber:{AMBER}; --amber2:{AMBER2}; --text:{TEXT}; --muted:{MUTED}; --mono:{MONO}; }}
html, body, .stApp, [data-testid="stAppViewContainer"] {{ background:var(--bg) !important; color:var(--text);
        font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stToolbar"] {{ right:1rem; }}
.block-container {{ padding-top:1.4rem; padding-bottom:3rem; max-width:1440px; }}
h1,h2,h3,h4 {{ font-family:Inter,sans-serif; letter-spacing:-0.01em; color:var(--text); }}
.q-mono, .q-num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}
.q-muted {{ color:var(--muted); }}
.q-card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:18px 20px; margin-bottom:14px; }}
.q-section {{ font-size:0.72rem; letter-spacing:0.14em; text-transform:uppercase; color:var(--muted); margin:6px 0 10px; font-weight:600; }}
.q-logo {{ display:flex; align-items:center; gap:10px; font-weight:700; font-size:1.35rem; }}
.q-mark {{ color:var(--jade); font-size:1.1rem; }}
.q-ar {{ color:var(--muted); font-weight:500; font-size:1.15rem; }}
.q-live {{ font-family:var(--mono); font-size:0.7rem; color:var(--jade); border:1px solid var(--border);
        padding:3px 8px; border-radius:20px; margin-left:8px; font-weight:500; }}
.q-live .dot {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:var(--jade);
        margin-right:6px; animation:qpulse 1.8s infinite; vertical-align:middle; }}
@keyframes qpulse {{ 0%{{opacity:1}} 50%{{opacity:.25}} 100%{{opacity:1}} }}
.q-badge {{ display:inline-block; font-size:0.78rem; font-weight:600; padding:6px 12px; border-radius:20px;
        border:1px solid var(--jade); color:var(--jade); background:rgba(16,185,129,0.08); }}
.q-badge.er {{ border-color:var(--amber); color:var(--amber); background:rgba(234,179,8,0.08); }}
.q-navline {{ border-bottom:1px solid var(--border); margin:6px 0 14px; }}
/* hero / role gate */
.q-hero {{ text-align:center; padding:56px 0 26px; }}
.q-hero h1 {{ font-size:2.5rem; margin-bottom:6px; }}
.q-hero p {{ color:var(--muted); font-size:1.1rem; }}
.q-hero .q-stats {{ font-family:var(--mono); font-size:0.8rem; color:var(--muted); margin-top:16px; }}
.q-role {{ background:var(--card); border:1px solid var(--border); border-radius:16px; padding:28px 26px; min-height:190px;
        transition:border-color .2s; }}
.q-role:hover {{ border-color:var(--jade); }}
.q-role .ic {{ font-size:1.6rem; margin-bottom:10px; }}
.q-role h3 {{ margin:0 0 8px; font-size:1.25rem; }}
.q-role p {{ color:var(--muted); font-size:0.95rem; line-height:1.5; margin:0; }}
/* bands */
.q-bands {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:14px; }}
.q-band {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px; }}
.q-band.mid {{ border-color:var(--jade); box-shadow:0 0 0 1px rgba(16,185,129,.25) inset; }}
.q-band .lab {{ font-size:0.72rem; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
.q-band .val {{ font-family:var(--mono); font-size:1.75rem; font-weight:700; margin-top:6px; }}
.q-band.mid .val {{ color:var(--jade); }}
.q-band .sub {{ font-family:var(--mono); font-size:0.78rem; color:var(--muted); margin-top:2px; }}
/* flags */
.q-flag {{ border-radius:10px; padding:12px 16px; margin-bottom:14px; font-size:0.95rem; border:1px solid; }}
.q-flag.warn {{ border-color:var(--amber); background:rgba(234,179,8,.08); color:var(--amber); }}
.q-flag.good {{ border-color:var(--jade); background:rgba(16,185,129,.08); color:var(--jade); }}
.q-flag.neutral {{ border-color:var(--border); background:var(--card); color:var(--text); }}
.q-flag b {{ font-family:var(--mono); }}
/* pills */
.q-pill {{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:0.72rem; font-weight:600; white-space:nowrap; border:1px solid; }}
.q-pill.prem {{ color:var(--jade); border-color:rgba(16,185,129,.5); background:rgba(16,185,129,.08); }}
.q-pill.neu {{ color:var(--muted); border-color:var(--border); }}
.q-pill.disc {{ color:var(--amber); border-color:rgba(234,179,8,.5); background:rgba(234,179,8,.08); }}
.q-chip {{ display:inline-block; padding:3px 10px; margin:0 6px 6px 0; border-radius:6px; border:1px solid var(--border);
        background:#0F1D18; font-size:0.8rem; }}
.q-chip .n {{ font-family:var(--mono); color:var(--jade); margin-left:6px; }}
/* tables */
table.q-table {{ width:100%; border-collapse:collapse; font-size:0.86rem; }}
table.q-table th {{ text-align:left; color:var(--muted); font-weight:600; font-size:0.7rem; letter-spacing:.1em;
        text-transform:uppercase; padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }}
table.q-table td {{ padding:8px 10px; border-bottom:1px solid rgba(30,58,48,.6); vertical-align:middle; }}
table.q-table tr:hover td {{ background:rgba(16,185,129,.04); }}
table.q-table td.r, table.q-table th.r {{ text-align:right; }}
.up {{ color:var(--jade); }} .down {{ color:var(--amber); }}
.q-bar {{ display:inline-block; height:6px; border-radius:3px; background:var(--border); width:70px; vertical-align:middle; margin-left:8px; position:relative; }}
.q-bar > span {{ position:absolute; left:0; top:0; height:6px; border-radius:3px; }}
.q-kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:14px; }}
.q-kpi {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }}
.q-kpi .lab {{ font-size:0.7rem; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
.q-kpi .val {{ font-family:var(--mono); font-size:1.4rem; font-weight:700; margin-top:4px; }}
.q-meter {{ height:10px; border-radius:5px; background:var(--border); overflow:hidden; margin-top:10px; }}
.q-meter > span {{ display:block; height:10px; }}
/* widgets */
.stTabs [data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid var(--border); }}
.stTabs [data-baseweb="tab"] {{ background:transparent; color:var(--muted); padding:10px 16px; font-weight:600; }}
.stTabs [aria-selected="true"] {{ color:var(--text) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--jade) !important; }}
.stButton > button, .stDownloadButton > button {{ border-radius:8px; border:1px solid var(--border); font-weight:600; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color:var(--jade); color:var(--jade); }}
.stButton > button[kind="primary"] {{ background:var(--jade); border-color:var(--jade); color:#04110C; }}
.stButton > button[kind="primary"]:hover {{ background:var(--jade2); color:#04110C; }}
[data-testid="stFileUploaderDropzone"] {{ background:#0F1D18; border:1px dashed var(--border); }}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color:var(--border) !important; }}
input, textarea {{ font-family:var(--mono) !important; }}
[data-testid="stMarkdownContainer"] code {{ color:var(--jade); background:#0F1D18; }}
.q-brief h1 {{ font-size:1.3rem; }} .q-brief h2 {{ font-size:1rem; margin-top:1rem; color:var(--jade); }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PLOT_LAYOUT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                   font=dict(family="Inter, sans-serif", color=MUTED, size=12),
                   margin=dict(l=10, r=30, t=10, b=10),
                   hoverlabel=dict(bgcolor=CARD, bordercolor=BORDER, font=dict(family=MONO, color=TEXT)))
PLOT_CONFIG = {"displayModeBar": False}

SAMPLE_CV = """Ahmed R. — Data & Analytics Associate, Dubai
Summary: 5 years building machine learning models and data pipelines for a regional bank.
Experience: Developed credit-risk scoring models in Python (scikit-learn, XGBoost) and deployed them with MLOps on AWS.
Built ETL pipelines in Airflow and Spark feeding Power BI dashboards for the CFO office.
Supported IFRS 9 expected credit loss reporting and Basel stress testing.
Prepared financial modeling and DCF valuation packs for an M&A due diligence workstream.
Education: MSc Business Analytics. CFA Level II candidate."""

SAMPLE_JD = """Senior Food Safety & Quality Lead — FMCG manufacturer, Abu Dhabi
We are hiring a Food Safety lead to own HACCP and ISO 22000 / FSSC 22000 compliance across two plants,
run GMP and Dubai Municipality / ADAFSA audits, and partner with demand planning (S&OP) and the supply chain team.
You will build quality dashboards in Power BI and support ESG and sustainability reporting on packaging waste."""


# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------
def H(s: str):
    st.markdown(s, unsafe_allow_html=True)


def esc(s) -> str:
    return html.escape(str(s))


def aed(x, sign=False) -> str:
    if x is None:
        return "—"
    return f"AED {x:+,.0f}" if sign else f"AED {x:,.0f}"


def tag_pill(tag: str) -> str:
    cls = {"AI Premium": "prem", "Automation Discount": "disc"}.get(tag, "neu")
    return f'<span class="q-pill {cls}">{esc(tag)}</span>'


def pct_html(p: float) -> str:
    cls = "up" if p > 0 else ("down" if p < 0 else "q-muted")
    arrow = "▲" if p > 0 else ("▼" if p < 0 else "■")
    return f'<span class="q-mono {cls}">{arrow} {p:+.1f}%</span>'


def score_bar(score: float, pivot: float) -> str:
    color = JADE if score < pivot else AMBER
    return (f'<span class="q-mono">{score:.0f}</span><span class="q-bar"><span style="width:{score:.0f}%;'
            f'background:{color}"></span></span>')


def spark_svg(vals, w=120, h=30) -> str:
    if not vals or len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pts = " ".join(f"{2 + i * (w - 4) / (len(vals) - 1):.1f},{h - 3 - (v - lo) / rng * (h - 6):.1f}"
                   for i, v in enumerate(vals))
    color = JADE if vals[-1] >= vals[0] else AMBER
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline fill="none" stroke="{color}" '
            f'stroke-width="1.6" stroke-linejoin="round" points="{pts}"/></svg>')


def text_hash(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()[:8]


def read_upload(f) -> str:
    if f is None:
        return ""
    data = f.getvalue()
    if f.name.lower().endswith(".pdf"):
        text = ""
        try:
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        except Exception:
            text = ""
        if len(text.strip()) < 40:
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            except Exception:
                pass
        return text
    return data.decode("utf-8", errors="ignore")


def load_market() -> engine.MarketData:
    """Re-read /data on every rerun — no caching, so file edits show up immediately."""
    try:
        return engine.load_data()
    except engine.DataError as exc:
        st.error(f"**Data Room problem:** {exc}")
        st.stop()


# ------------------------------------------------------------------------------------
# Shared components
# ------------------------------------------------------------------------------------
def band_cards(res: dict, labels=("P25 · Conservative", "P50 · Fair Market Value", "P75 · Top-Decile Talent")):
    b = res["bands"]
    cells = []
    for (k, cls), lab in zip([("p25", ""), ("p50", "mid"), ("p75", "")], labels):
        cells.append(f'<div class="q-band {cls}"><div class="lab">{esc(lab)}</div>'
                     f'<div class="val">{aed(b[k])}</div>'
                     f'<div class="sub">per month · {aed(b[k] * 12)} / yr</div></div>')
    H('<div class="q-bands">' + "".join(cells) + "</div>")


def waterfall_chart(res: dict, height=420):
    wf = res["waterfall"]
    y = [s["step"] for s in wf] + ["P50 Fair Market Value"]
    x = [s["delta_aed"] for s in wf] + [None]
    measure = ["absolute"] + ["relative"] * (len(wf) - 1) + ["total"]
    text = [aed(wf[0]["delta_aed"])] + [aed(s["delta_aed"], sign=True) for s in wf[1:]] + [aed(res["bands"]["p50"])]
    notes = [s["note"] for s in wf] + ["Rounded to nearest AED 100"]
    fig = go.Figure(go.Waterfall(
        orientation="h", measure=measure, y=y, x=x, text=text, textposition="outside",
        textfont=dict(family=MONO, color=TEXT, size=12), customdata=notes,
        hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
        connector=dict(line=dict(color=BORDER, width=1)),
        increasing=dict(marker=dict(color=JADE)), decreasing=dict(marker=dict(color=AMBER)),
        totals=dict(marker=dict(color=JADE2, line=dict(color=TEXT, width=1)))))
    fig.update_layout(**PLOT_LAYOUT, height=height, showlegend=False)
    fig.update_yaxes(autorange="reversed", tickfont=dict(color=TEXT, size=12))
    fig.update_xaxes(gridcolor=BORDER, zeroline=False, tickprefix="AED ", tickformat=",",
                     tickfont=dict(family=MONO, size=11), range=[0, max(s["running_aed"] for s in res["waterfall"]) * 1.32])
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)


def waterfall_table(res: dict):
    rows = "".join(
        f'<tr><td>{esc(s["step"])}</td><td class="q-muted">{esc(s["note"])}</td>'
        f'<td class="r q-mono {"up" if s["delta_aed"] > 0 and i else ("down" if s["delta_aed"] < 0 else "")}">'
        f'{aed(s["delta_aed"], sign=bool(i))}</td><td class="r q-mono">{aed(s["running_aed"])}</td></tr>'
        for i, s in enumerate(res["waterfall"]))
    H('<table class="q-table"><tr><th>Step</th><th>Factor</th><th class="r">Δ AED/mo</th>'
      f'<th class="r">Running</th></tr>{rows}<tr><td><b>P50 Fair Market Value</b></td>'
      f'<td class="q-muted">P25 = ×{res["bands"]["p25"] / res["bands"]["p50"]:.2f} · P75 = ×'
      f'{res["bands"]["p75"] / res["bands"]["p50"]:.2f}</td><td></td><td class="r q-mono up"><b>'
      f'{aed(res["bands"]["p50"])}</b></td></tr></table>')


def bundle_table(res: dict, md: engine.MarketData):
    rows = "".join(
        f'<tr><td>{esc(s["skill_name"])}<div class="q-muted q-mono" style="font-size:.72rem">{esc(s["skill_id"])}'
        f' · {esc(s["category"])}{" · cross-domain" if s["complementary"] else ""}</div></td>'
        f'<td class="r q-mono">{s["weight"] * 100:.1f}%</td><td class="r q-mono">{aed(s["base_monthly_aed"])}</td>'
        f'<td class="r q-mono">{aed(s["weighted_aed"])}</td><td class="r">{pct_html(s["pct_change_30d"])}</td>'
        f'<td>{score_bar(s["ai_replaceability_score"], md.multipliers["ai_adjustment"]["pivot_score"])}</td>'
        f'<td>{tag_pill(s["ai_tag"])}</td></tr>' for s in res["skills"])
    H('<table class="q-table"><tr><th>Skill</th><th class="r">Weight</th><th class="r">Index AED/mo</th>'
      '<th class="r">Weighted</th><th class="r">30D</th><th>AI Replaceability</th><th>Tag</th></tr>'
      f'{rows}</table>')


def comps_table(res: dict, md: engine.MarketData):
    comps = res["comps"]
    if comps is None or comps.empty:
        cfg = md.multipliers["comps"]
        gap = cfg.get("max_years_gap")
        H(f'<div class="q-muted">No verified offers match this emirate with ≥{cfg.get("min_skill_overlap", 1)} '
          f'shared skill{f" within ±{gap} yrs experience" if gap is not None else ""}. P50 uses the index only.</div>')
        return
    rows = "".join(
        f'<tr><td>{esc(r.role_title)}</td><td>{esc(r.emirate)}</td><td class="r q-mono">{r.years_exp:.0f}</td>'
        f'<td>{esc(r.education)}</td><td class="q-muted" style="font-size:.8rem">{esc(r.skills_list)}</td>'
        f'<td class="r q-mono">{r.skill_overlap}</td><td class="r q-mono">{aed(r.verified_monthly_aed)}</td>'
        f'<td class="q-muted" style="font-size:.8rem">{esc(r.source_type)}</td></tr>'
        for r in comps.itertuples())
    H('<table class="q-table"><tr><th>Role</th><th>Emirate</th><th class="r">Yrs</th><th>Education</th>'
      '<th>Skills</th><th class="r">Overlap</th><th class="r">Verified AED/mo</th><th>Source</th></tr>'
      f'{rows}</table><div class="q-muted q-mono" style="font-size:.78rem;margin-top:8px">Median '
      f'{aed(engine.round_aed(res["comps_median"], md))} · blended '
      f'{md.multipliers["comps"]["offers_weight"] * 100:.0f}% into P50</div>')


def market_ticker_html(df: pd.DataFrame, md: engine.MarketData) -> str:
    pivot = md.multipliers["ai_adjustment"]["pivot_score"]
    rows = "".join(
        f'<tr><td>{esc(r.skill_name)}<div class="q-muted" style="font-size:.72rem">{esc(r.category)}</div></td>'
        f'<td class="q-mono q-muted">{esc(r.skill_id)}</td>'
        f'<td class="r q-mono"><b>{aed(r.base_monthly_aed)}</b></td>'
        f'<td class="r">{pct_html(r.pct_change_30d)}</td>'
        f'<td>{spark_svg(r.sparkline)}</td>'
        f'<td>{score_bar(r.ai_replaceability_score, pivot)}</td>'
        f'<td class="r q-mono">×{r.ai_factor:.3f}</td>'
        f'<td>{tag_pill(r.ai_tag)}</td>'
        f'<td class="r q-mono q-muted">{r.sample_size:,}</td></tr>'
        for r in df.itertuples())
    return ('<div class="q-card" style="padding:6px 8px;overflow-x:auto"><table class="q-table">'
            '<tr><th>Skill Name</th><th>Skill Code</th><th class="r">Price AED/mo</th><th class="r">30-Day %</th>'
            '<th>30-Day Sparkline</th><th>AI Replaceability 0–100</th><th class="r">AI Factor</th>'
            '<th>AI Adjustment Tag</th><th class="r">n</th></tr>' + rows + '</table></div>')


def market_filters(md: engine.MarketData, prefix: str) -> pd.DataFrame:
    df = engine.market_table(md)
    c1, c2, c3 = st.columns([2, 2.4, 1.6])
    q = c1.text_input("Search skills", key=f"{prefix}_q", placeholder="e.g. AI, finance, QA")
    cats = c2.multiselect("Category", sorted(df["category"].unique()), key=f"{prefix}_cat")
    sort = c3.selectbox("Sort by", ["Price (high → low)", "30-day trend (rising first)",
                                    "AI replaceability (safest first)", "AI replaceability (most exposed first)",
                                    "Skill name"], key=f"{prefix}_sort")
    if q:
        ql = q.lower()
        df = df[df["skill_name"].str.lower().str.contains(ql, regex=False)
                | df["category"].str.lower().str.contains(ql, regex=False)
                | df["skill_id"].str.lower().str.contains(ql, regex=False)]
    if cats:
        df = df[df["category"].isin(cats)]
    by = {"Price (high → low)": ("base_monthly_aed", False),
          "30-day trend (rising first)": ("pct_change_30d", False),
          "AI replaceability (safest first)": ("ai_replaceability_score", True),
          "AI replaceability (most exposed first)": ("ai_replaceability_score", False),
          "Skill name": ("skill_name", True)}[sort]
    return df.sort_values(by[0], ascending=by[1])


# ------------------------------------------------------------------------------------
# Data Room
# ------------------------------------------------------------------------------------
# Public deployments lock the Data Room: a READ_ONLY file next to app.py (or QIMAH_READ_ONLY=1) disables uploads,
# because every visitor of a hosted app shares one /data folder.
READ_ONLY = (Path(__file__).resolve().parent / "READ_ONLY").exists() or \
    os.environ.get("QIMAH_READ_ONLY", "").strip().lower() in {"1", "true", "yes"}


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)
    return stem or f"upload_{dt.datetime.now():%Y%m%d_%H%M%S}.csv"


def render_data_room(md: engine.MarketData, prefix: str):
    flash = st.session_state.pop("data_flash", None)
    if flash:
        st.success(flash)
    H(f'<div class="q-section">Data Room · <span class="q-mono">{esc(md.data_dir)}</span></div>')
    rows = "".join(
        f'<tr><td class="q-mono">{esc(f.name)}</td><td>{esc(f.kind)}</td>'
        f'<td class="r q-mono">{"" if f.rows is None else f"{f.rows:,}"}</td>'
        f'<td><span class="q-pill {"prem" if f.status == "active" else ("disc" if f.status == "error" else "neu")}">'
        f'{esc(f.status)}</span></td><td class="r q-mono q-muted">{f.size_bytes / 1024:.1f} KB</td>'
        f'<td class="q-mono q-muted">{esc(f.modified)}</td><td class="q-muted" style="font-size:.8rem">{esc(f.detail)}</td></tr>'
        for f in md.files)
    H('<div class="q-card" style="padding:6px 8px"><table class="q-table"><tr><th>File</th><th>Detected as</th>'
      '<th class="r">Rows</th><th>Status</th><th class="r">Size</th><th>Modified</th><th>Detail</th></tr>'
      f'{rows}</table></div>')
    H(f'<div class="q-muted q-mono" style="font-size:.8rem;margin-bottom:10px">In use: {len(md.skills)} skills · '
      f'{len(md.offers)} verified offers · {md.history["skill_id"].nunique() if not md.history.empty else 0} '
      f'price histories · model {esc(md.multipliers.get("model_version", "—"))} · read at '
      f'{dt.datetime.now():%H:%M:%S}</div>')
    for w in md.warnings:
        st.warning(w)

    if st.button("↻ Reload /data folder", key=f"{prefix}_reload"):
        st.session_state["data_flash"] = f"Reloaded /data at {dt.datetime.now():%H:%M:%S}."
        st.rerun()

    if READ_ONLY:
        H('<div class="q-section" style="margin-top:16px">Drop new files into /data</div>')
        st.info("Uploads are switched off in this public demo so every viewer sees the same data. "
                "Run Qimah locally to drop new .csv/.json files into /data and watch the index update live.")
        return

    H('<div class="q-section" style="margin-top:16px">Drop new files into /data</div>')
    st.caption("CSV files are recognised by their columns (skill index, verified offers or price history); "
               "JSON files as multipliers or a keyword map. New skill rows override matching skill_ids.")
    nonce = st.session_state.setdefault("upload_nonce", 0)
    ups = st.file_uploader("Upload .csv or .json", type=["csv", "json"], accept_multiple_files=True,
                           key=f"{prefix}_up_{nonce}", label_visibility="collapsed")
    plans = []
    for up in ups or []:
        raw = up.getvalue()
        name = _safe_name(up.name)
        try:
            if name.lower().endswith(".csv"):
                df = pd.read_csv(io.BytesIO(raw))
                kind, missing = engine.classify_columns(df.columns)
                info = f"{len(df)} rows"
            else:
                obj = json.loads(raw.decode("utf-8"))
                df, missing = None, []
                kind = engine.classify_json(obj)
                info = f"{len(obj)} keys"
        except Exception as exc:
            st.error(f"{up.name}: could not be parsed — {exc}")
            continue
        exists = (md.data_dir / name).exists()
        label = f"**{esc(name)}** → detected as `{kind}` ({info})"
        if missing:
            label += f" · missing: {', '.join(missing)} (will be ignored by the engine)"
        st.markdown(label)
        mode = "save"
        if kind == "offers" and name != "verified_offers.csv":
            mode = st.radio("How should these offers be added?", ["Append rows to verified_offers.csv",
                                                                  "Save as a separate file"],
                            key=f"{prefix}_mode_{nonce}_{name}", horizontal=True)
            mode = "append" if mode.startswith("Append") else "save"
        if mode == "save" and exists:
            st.caption(f"⚠ {name} already exists in /data and will be replaced.")
        plans.append((name, raw, kind, mode, df))

    if plans and st.button("Ingest into /data", type="primary", key=f"{prefix}_ingest_{nonce}"):
        done = []
        for name, raw, kind, mode, df in plans:
            if mode == "append":
                target = md.data_dir / "verified_offers.csv"
                df = df.copy()
                df.columns = [re.sub(r"\s+", "_", str(c).strip().lower()) for c in df.columns]
                if target.exists():
                    existing = pd.read_csv(target)
                    out = pd.concat([existing, df[engine.OFFER_COLS]], ignore_index=True)
                else:
                    out = df[engine.OFFER_COLS]
                out.to_csv(target, index=False)
                done.append(f"appended {len(df)} offers to verified_offers.csv")
            else:
                (md.data_dir / name).write_bytes(raw)
                done.append(f"saved {name}")
        st.session_state["upload_nonce"] = nonce + 1
        st.session_state["data_flash"] = "Data Room updated: " + "; ".join(done) + "."
        st.rerun()


_dialog = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
if _dialog is not None:
    @_dialog("Data Room · /data live sync", width="large")
    def data_room_dialog():
        render_data_room(load_market(), "dlg")
else:
    data_room_dialog = None


# ------------------------------------------------------------------------------------
# Navigation & role gate
# ------------------------------------------------------------------------------------
def live_label(md: engine.MarketData) -> str:
    latest = max((f.modified for f in md.files), default="")
    return (f'<span class="q-live"><span class="dot"></span>LIVE · {len([f for f in md.files if f.status == "active"])}'
            f' files · /data {esc(latest[5:])}</span>')


def role_gate(md: engine.MarketData):
    n_points = int(md.skills["sample_size"].sum())
    H(f'<div class="q-hero"><div class="q-logo" style="justify-content:center;font-size:1.1rem">'
      f'<span class="q-mark">◆</span> Qimah <span class="q-ar">قيمة</span>{live_label(md)}</div>'
      f'<h1>Welcome to Qimah (قيمة).</h1><p>How are you using the terminal today?</p>'
      f'<div class="q-stats">Indexing {len(md.skills)} UAE skills · {len(md.offers)} verified offers · '
      f'{n_points:,} market data points · all figures AED/month</div></div>')
    _, a, b, _ = st.columns([0.5, 2, 2, 0.5], gap="large")
    with a:
        H('<div class="q-role"><div class="ic">👤</div><h3>I am an Employee / Talent</h3>'
          '<p>Discover what your skills are worth in the UAE, spot underpayment, and generate a '
          'data-backed negotiation brief.</p></div>')
        if st.button("Continue as Employee →", key="gate_emp", type="primary", use_container_width=True):
            st.session_state.user_role = "Employee"
            st.rerun()
    with b:
        H('<div class="q-role"><div class="ic">🏢</div><h3>I am an Employer / Hiring Team</h3>'
          '<p>Benchmark real-time hiring budgets, price multi-skill roles, and check AI future-proofing '
          'before making an offer.</p></div>')
        if st.button("Continue as Employer →", key="gate_er", type="primary", use_container_width=True):
            st.session_state.user_role = "Employer"
            st.rerun()


def top_nav(md: engine.MarketData):
    role = st.session_state.user_role
    c1, c2, c3, c4 = st.columns([4.2, 1.6, 2.4, 1.8], vertical_alignment="center")
    c1.markdown(f'<div class="q-logo"><span class="q-mark">◆</span> Qimah <span class="q-ar">قيمة</span>'
                f'{live_label(md)}</div>', unsafe_allow_html=True)
    badge = ('<span class="q-badge">● Employee / Talent</span>' if role == "Employee"
             else '<span class="q-badge er">● Employer / Hiring</span>')
    c2.markdown(badge, unsafe_allow_html=True)
    other = "Employer" if role == "Employee" else "Employee"
    if c3.button(f"⇄ Switch Role (Employee ↔ Employer)", key="switch_role", use_container_width=True):
        st.session_state.user_role = other
        st.rerun()
    if c4.button("▤ Data Room (/data)", key="open_dr", use_container_width=True):
        if data_room_dialog:
            data_room_dialog()
        else:
            st.session_state.show_dr = not st.session_state.get("show_dr", False)
    H('<div class="q-navline"></div>')
    if data_room_dialog is None and st.session_state.get("show_dr"):
        with st.container(border=True):
            render_data_room(md, "inline_nav")


# ------------------------------------------------------------------------------------
# Employee workspace
# ------------------------------------------------------------------------------------
def _load_sample_cv():
    st.session_state["emp_cv_text"] = SAMPLE_CV


def employee_valuator(md: engine.MarketData):
    left, right = st.columns([1, 1.65], gap="large")
    with left:
        H('<div class="q-section">1 · Your CV</div>')
        up = st.file_uploader("Upload CV (.pdf or .txt)", type=["pdf", "txt"], key="emp_cv_file")
        st.text_area("…or paste CV text", key="emp_cv_text", height=150,
                     placeholder="Paste your CV or LinkedIn summary here")
        st.button("Load sample CV", key="emp_sample", on_click=_load_sample_cv)
        cv_text = (read_upload(up) + "\n" + st.session_state.get("emp_cv_text", "")).strip()
        if up is not None and not read_upload(up).strip():
            st.warning("No text could be extracted from that PDF (it may be scanned). Paste the text instead.")
        found = engine.extract_skills(cv_text, md)
        h = text_hash(cv_text)

        H('<div class="q-section" style="margin-top:14px">2 · Profile</div>')
        if found:
            chips = "".join(f'<span class="q-chip">{esc(d["skill_name"])}<span class="n">×{d["hits"]}</span></span>'
                            for d in found)
            H(f'<div class="q-muted" style="font-size:.8rem;margin-bottom:6px">Detected {len(found)} indexed '
              f'skill{"s" if len(found) != 1 else ""} (keyword hits):</div>{chips}')
        all_ids = md.skills["skill_id"].tolist()
        skill_ids = st.multiselect("Skills used for valuation (top 5, editable)", all_ids,
                                   default=[d["skill_id"] for d in found[:5]], max_selections=5,
                                   format_func=md.skill_name, key=f"emp_skills_{h}")
        emirates = md.emirates
        emirate = st.selectbox("Emirate", emirates, index=emirates.index("Dubai") if "Dubai" in emirates else 0,
                               key="emp_emirate")
        c1, c2 = st.columns(2)
        cv_years = engine.detect_years(cv_text)
        years = c1.number_input("Years of experience", 0, 45, cv_years if cv_years is not None else 3, step=1,
                                key=f"emp_years_{h}",
                                help="Pre-filled from your CV when it states years of experience; edit freely.")
        tier = engine.experience_tier(md, years=years)
        c2.markdown(f'<div style="padding-top:30px" class="q-muted q-mono">{esc(tier["label"])} · ×'
                    f'{tier["multiplier"]:.2f}</div>', unsafe_allow_html=True)
        education = st.selectbox("Education", md.education_levels, key="emp_edu")
        certs = st.multiselect("Tier-1 certifications", md.tier1_certs, default=engine.detect_certs(cv_text, md),
                               key=f"emp_certs_{h}")
        current = st.number_input("Current / offered monthly salary (AED, optional)", 0, 1_000_000, 0,
                                  step=500, key="emp_current")

    with right:
        if not skill_ids:
            H('<div class="q-card" style="text-align:center;padding:60px 20px"><div class="q-mark" '
              'style="font-size:1.6rem">◆</div><h3>Price your skills</h3><p class="q-muted">Upload or paste a CV '
              '(or pick skills on the left) to see your P25–P50–P75 range, the AED waterfall behind it and a '
              'negotiation brief.</p></div>')
            st.session_state.pop("employee_profile", None)
            return
        profile = dict(skill_ids=skill_ids, emirate=emirate, education=education, years=years, certs=certs)
        st.session_state["employee_profile"] = profile
        res = engine.value_profile(md, **profile)

        H('<div class="q-section">Your market value · AED / month</div>')
        band_cards(res)
        pos = engine.salary_position(md, res, current)
        if pos:
            gap = pos["gap_monthly"]
            word = "below" if gap < 0 else "above"
            H(f'<div class="q-flag {pos["tone"]}">{esc(pos["status"])}: <b>{aed(gap, sign=True)}</b> {word} '
              f'market/mo vs P50 (<b>{aed(pos["gap_annual"], sign=True)}</b> per year, '
              f'<b>{pos["gap_pct"] * 100:+.1f}%</b>). You entered {aed(pos["current"])}.</div>')
        H(f'<div class="q-muted" style="font-size:.85rem;margin-bottom:6px">{tag_pill(res["ai_tag"])} '
          f'&nbsp;AI replaceability <span class="q-mono">{res["ai_score"]:.0f}/100</span> · factor '
          f'<span class="q-mono">×{res["a_ai"]:.3f}</span> · demand velocity <span class="q-mono">'
          f'×{res["demand_velocity"]:.3f}</span> · comps used <span class="q-mono">{len(res["comps"])}</span></div>')
        H('<div class="q-section" style="margin-top:12px">AED waterfall · how your P50 is built</div>')
        waterfall_chart(res)
        with st.expander("Step-by-step calculation", expanded=False):
            waterfall_table(res)
        with st.expander("Skill bundle & weights", expanded=False):
            bundle_table(res, md)
        with st.expander(f"Matched verified offers ({len(res['comps'])})", expanded=False):
            comps_table(res, md)

        H('<div class="q-section" style="margin-top:14px">Negotiation Brief</div>')
        brief = engine.negotiation_brief(md, res, current=current or None)
        with st.container(border=True):
            st.markdown(brief.replace("# Qimah Negotiation Brief", "#### Qimah Negotiation Brief", 1)
                        .replace("\n## ", "\n##### "))
        st.download_button("⬇ Download brief (.md)", brief, file_name=f"qimah_negotiation_brief_{dt.date.today()}.md",
                           mime="text/markdown", key="emp_dl")


def employee_ticker(md: engine.MarketData):
    H('<div class="q-section">Live Skill Ticker · index price at 2–3 yrs baseline, before emirate & credentials</div>')
    df = market_filters(md, "emp_tk")
    H(market_ticker_html(df, md))

    H('<div class="q-section" style="margin-top:18px">Skill Upskilling Simulator</div>')
    profile = st.session_state.get("employee_profile")
    custom = False
    if profile:
        names = ", ".join(md.skill_name(s) for s in profile["skill_ids"])
        H(f'<div class="q-muted" style="font-size:.88rem;margin-bottom:8px">Starting from your CV profile: '
          f'<b style="color:{TEXT}">{esc(names)}</b> · {esc(profile["emirate"])} · '
          f'{profile["years"]} yrs · {esc(profile["education"])}</div>')
        custom = st.toggle("Use a different starting profile", key="sim_custom")
    if not profile or custom:
        c1, c2, c3, c4 = st.columns([2.4, 1.2, 1, 1.4])
        sids = c1.multiselect("Current skills", md.skills["skill_id"].tolist(), default=["FIN-FMOD"]
                              if "FIN-FMOD" in md.skills["skill_id"].values else None,
                              max_selections=5, format_func=md.skill_name, key="sim_skills")
        em = c2.selectbox("Emirate", md.emirates, key="sim_em")
        yrs = c3.number_input("Years", 0, 45, 3, key="sim_yrs")
        edu = c4.selectbox("Education", md.education_levels, key="sim_edu")
        if not sids:
            st.info("Pick at least one current skill to simulate upskilling.")
            return
        profile = dict(skill_ids=sids, emirate=em, education=edu, years=yrs, certs=[])
    held = set(profile["skill_ids"])
    options = [s for s in md.skills["skill_id"] if s not in held]
    add = st.multiselect("Add 1–2 skills", options, max_selections=2, format_func=md.skill_name, key="sim_add")
    base = engine.value_profile(md, **profile)
    scan = engine.upskill_scan(md, profile)

    if add:
        new = engine.simulate_with(md, profile, add)
        delta = new["bands"]["p50"] - base["bands"]["p50"]
        color = JADE if delta >= 0 else AMBER
        dropped = [md.skill_name(s) for s in list(held) + add if s not in new["inputs"]["skill_ids"]]
        H(f'<div class="q-kpis" style="grid-template-columns:repeat(3,1fr)">'
          f'<div class="q-kpi"><div class="lab">Today · P50</div><div class="val">{aed(base["bands"]["p50"])}</div></div>'
          f'<div class="q-kpi"><div class="lab">With new skill{"s" if len(add) > 1 else ""} · P50</div>'
          f'<div class="val" style="color:{color}">{aed(new["bands"]["p50"])}</div></div>'
          f'<div class="q-kpi"><div class="lab">Change / month</div><div class="val" style="color:{color}">'
          f'{aed(delta, sign=True)}</div><div class="q-muted q-mono" style="font-size:.78rem">'
          f'{aed(delta * 12, sign=True)} / yr · {delta / base["bands"]["p50"] * 100:+.1f}%</div></div></div>')
        if dropped:
            st.caption("Bundle capped at 5 skills — lowest-priced dropped out: " + ", ".join(dropped))
        if delta < 0:
            st.caption("A lower-priced skill dilutes the weighted bundle base; the gain from synergy or AI "
                       "safety is not enough to offset it here.")
    H('<div class="q-muted" style="font-size:.8rem;margin:10px 0 6px">Highest-impact single additions for this profile:</div>')
    top = scan.head(6)
    rows = "".join(
        f'<tr><td>{esc(r.skill_name)}<div class="q-muted" style="font-size:.72rem">{esc(r.category)}</div></td>'
        f'<td>{tag_pill(r.ai_tag)}</td><td class="r q-mono">{aed(r.new_p50)}</td>'
        f'<td class="r q-mono {"up" if r.delta_aed > 0 else "down"}">{aed(r.delta_aed, sign=True)}</td></tr>'
        for r in top.itertuples())
    H('<div class="q-card" style="padding:6px 8px"><table class="q-table"><tr><th>Add skill</th><th>AI tag</th>'
      f'<th class="r">New P50</th><th class="r">Δ AED/mo</th></tr>{rows}</table></div>')


# ------------------------------------------------------------------------------------
# Employer workspace
# ------------------------------------------------------------------------------------
def _load_sample_jd():
    st.session_state["er_jd"] = SAMPLE_JD


def employer_budget(md: engine.MarketData):
    left, right = st.columns([1, 1.65], gap="large")
    with left:
        H('<div class="q-section">1 · Role definition</div>')
        st.text_area("Paste a job description to auto-extract skills (optional)", key="er_jd", height=150)
        st.button("Load sample JD", key="er_sample", on_click=_load_sample_jd)
        jd = st.session_state.get("er_jd", "")
        found = engine.extract_skills(jd, md)
        h = text_hash(jd)
        if found:
            chips = "".join(f'<span class="q-chip">{esc(d["skill_name"])}<span class="n">×{d["hits"]}</span></span>'
                            for d in found)
            H(f'<div class="q-muted" style="font-size:.8rem;margin:6px 0">Extracted from JD:</div>{chips}')
        skill_ids = st.multiselect("Required skills (up to 5)", md.skills["skill_id"].tolist(),
                                   default=[d["skill_id"] for d in found[:5]], max_selections=5,
                                   format_func=md.skill_name, key=f"er_skills_{h}")
        H('<div class="q-section" style="margin-top:14px">2 · Hiring parameters</div>')
        emirates = md.emirates
        emirate = st.selectbox("Target emirate", emirates,
                               index=emirates.index("Abu Dhabi") if "Abu Dhabi" in emirates else 0, key="er_em")
        tiers = md.experience_tiers
        tier_key = st.selectbox("Experience tier", [t["key"] for t in tiers], index=min(2, len(tiers) - 1),
                                format_func=lambda k: next(f'{t["label"]} · ×{t["multiplier"]:.2f}'
                                                           for t in tiers if t["key"] == k), key="er_tier")
        education = st.selectbox("Education requirement", md.education_levels, key="er_edu")
        certs = st.multiselect("Required Tier-1 certification", md.tier1_certs, key="er_certs")
        headcount = st.number_input("Headcount for this role", 1, 500, 1, key="er_hc")

    with right:
        if not skill_ids:
            H('<div class="q-card" style="text-align:center;padding:60px 20px"><div class="q-mark" '
              'style="font-size:1.6rem">◆</div><h3>Price a role</h3><p class="q-muted">Pick up to five required '
              'skills or paste a job description to get a P25–P75 hiring budget, its AI future-proofing score '
              'and matching verified offers.</p></div>')
            return
        res = engine.value_profile(md, skill_ids=skill_ids, emirate=emirate, education=education,
                                   tier_key=tier_key, certs=certs)
        H('<div class="q-section">Expected hiring cost · AED / month per hire</div>')
        band_cards(res, labels=("P25 · Competitive", "P50 · Market Median", "P75 · Top-Decile Talent"))

        b = res["bands"]
        fp = res["future_proof_score"]
        fp_color = JADE if res["ai_tag"] == "AI Premium" else (AMBER if res["ai_tag"] == "Automation Discount" else MUTED)
        H(f'<div class="q-kpis" style="grid-template-columns:1.4fr 1fr">'
          f'<div class="q-kpi"><div class="lab">Annual budget impact · {headcount} hire{"s" if headcount > 1 else ""}</div>'
          f'<div class="val">{aed(b["p50"] * 12 * headcount)}</div><div class="q-muted q-mono" style="font-size:.8rem">'
          f'range {aed(b["p25"] * 12 * headcount)} – {aed(b["p75"] * 12 * headcount)} · base monthly × 12</div></div>'
          f'<div class="q-kpi"><div class="lab">AI future-proofing score</div><div class="val" style="color:{fp_color}">'
          f'{fp}<span class="q-muted" style="font-size:.9rem">/100</span></div>'
          f'<div class="q-meter"><span style="width:{fp}%;background:{fp_color}"></span></div>'
          f'<div style="margin-top:8px">{tag_pill(res["ai_tag"])} <span class="q-muted q-mono" style="font-size:.78rem">'
          f'replaceability {res["ai_score"]:.0f}/100 · ×{res["a_ai"]:.3f}</span></div></div></div>')
        if res["ai_tag"] == "Automation Discount":
            H('<div class="q-flag warn">This role is weighted toward automatable work. Consider redesigning it around '
              'judgement-heavy skills before committing a multi-year budget.</div>')

        H('<div class="q-section" style="margin-top:6px">AED waterfall · role P50</div>')
        waterfall_chart(res, height=400)
        with st.expander("Step-by-step calculation"):
            waterfall_table(res)
        H('<div class="q-section">Role skill mix</div>')
        bundle_table(res, md)
        H(f'<div class="q-section" style="margin-top:16px">Matching anonymized comps ({len(res["comps"])})</div>')
        comps_table(res, md)


def employer_terminal(md: engine.MarketData):
    mt = engine.market_table(md)
    cats = st.multiselect("Department / category filter", sorted(mt["category"].unique()), key="er_term_cat")
    view = mt[mt["category"].isin(cats)] if cats else mt
    if view.empty:
        st.info("No skills in that selection.")
        return
    w = view["sample_size"].clip(lower=1)
    avg_trend = (view["pct_change_30d"] * w).sum() / w.sum()
    disc_share = w[view["ai_tag"] == "Automation Discount"].sum() / w.sum()
    prem_share = w[view["ai_tag"] == "AI Premium"].sum() / w.sum()
    H(f'<div class="q-kpis">'
      f'<div class="q-kpi"><div class="lab">Skills tracked</div><div class="val">{len(view)}</div></div>'
      f'<div class="q-kpi"><div class="lab">Wtd 30-day price change</div><div class="val" style="color:'
      f'{JADE if avg_trend >= 0 else AMBER}">{avg_trend:+.2f}%</div></div>'
      f'<div class="q-kpi"><div class="lab">Market in AI Premium skills</div><div class="val" style="color:{JADE}">'
      f'{prem_share * 100:.0f}%</div></div>'
      f'<div class="q-kpi"><div class="lab">Market in Automation Discount</div><div class="val" style="color:{AMBER}">'
      f'{disc_share * 100:.0f}%</div></div></div>')

    c1, c2 = st.columns(2, gap="large")
    with c1:
        H('<div class="q-section">Skill inflation / deflation · 30 days</div>')
        d = view.sort_values("pct_change_30d")
        fig = go.Figure(go.Bar(x=d["pct_change_30d"], y=d["skill_name"], orientation="h",
                               marker_color=[JADE if v >= 0 else AMBER for v in d["pct_change_30d"]],
                               text=[f"{v:+.1f}%" for v in d["pct_change_30d"]], textposition="outside",
                               textfont=dict(family=MONO, color=TEXT, size=11),
                               hovertemplate="%{y}: %{x:+.1f}%<extra></extra>"))
        fig.update_layout(**PLOT_LAYOUT, height=max(260, 26 * len(d) + 40))
        fig.update_xaxes(gridcolor=BORDER, zerolinecolor=MUTED, ticksuffix="%", tickfont=dict(family=MONO))
        fig.update_yaxes(tickfont=dict(color=TEXT))
        st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
    with c2:
        H('<div class="q-section">AI replaceability exposure by department</div>')
        sub = md.skills[md.skills["category"].isin(view["category"].unique())]
        tmp = engine.MarketData(skills=sub, offers=md.offers, history=md.history, multipliers=md.multipliers,
                                keywords=md.keywords)
        ce = engine.category_exposure(tmp).sort_values("avg_ai_score")
        pivot = md.multipliers["ai_adjustment"]["pivot_score"]
        fig2 = go.Figure(go.Bar(x=ce["avg_ai_score"], y=ce["category"], orientation="h",
                                marker_color=[JADE if v < pivot else AMBER for v in ce["avg_ai_score"]],
                                text=[f"{v:.0f}" for v in ce["avg_ai_score"]], textposition="outside",
                                textfont=dict(family=MONO, color=TEXT, size=12),
                                customdata=ce[["avg_pct_change_30d", "sample_size"]].values,
                                hovertemplate="%{y}<br>AI replaceability %{x:.0f}/100<br>30D %{customdata[0]:+.2f}%"
                                              "<br>n = %{customdata[1]:,}<extra></extra>"))
        fig2.add_vline(x=pivot, line=dict(color=MUTED, dash="dot", width=1),
                       annotation_text=f"neutral pivot {pivot}", annotation_font=dict(color=MUTED, size=10))
        fig2.update_layout(**PLOT_LAYOUT, height=max(260, 46 * len(ce) + 60))
        fig2.update_xaxes(range=[0, 100], gridcolor=BORDER, tickfont=dict(family=MONO))
        fig2.update_yaxes(tickfont=dict(color=TEXT))
        st.plotly_chart(fig2, use_container_width=True, config=PLOT_CONFIG)

    H('<div class="q-section">Live market index</div>')
    df = view.sort_values("base_monthly_aed", ascending=False)
    H(market_ticker_html(df, md))

    H('<div class="q-section" style="margin-top:18px">Data Room (/data Live Sync)</div>')
    with st.container(border=True):
        render_data_room(md, "er_term")


# ------------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------------
def main():
    if "user_role" not in st.session_state:
        st.session_state.user_role = None
    md = load_market()
    if st.session_state.user_role is None:
        role_gate(md)
        return
    top_nav(md)
    if st.session_state.user_role == "Employee":
        t1, t2 = st.tabs(["My CV & Offer Valuator", "Live Skill Ticker"])
        with t1:
            employee_valuator(md)
        with t2:
            employee_ticker(md)
    else:
        t1, t2 = st.tabs(["Role & Talent Budget Calculator", "UAE Compensation & AI Risk Terminal"])
        with t1:
            employer_budget(md)
        with t2:
            employer_terminal(md)
    H(f'<div class="q-muted q-mono" style="font-size:.72rem;margin-top:30px;border-top:1px solid {BORDER};'
      f'padding-top:10px">Qimah (قيمة) prototype · deterministic model {esc(md.multipliers.get("model_version", ""))}'
      f' · all figures AED/month, rounded to AED {md.multipliers.get("rounding_aed", 100)} · '
      f'source: ./data · not financial advice</div>')


main()
