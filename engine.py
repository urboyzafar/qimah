"""
Qimah (قيمة) — deterministic skill-pricing & CV-matching engine.

Everything here is pure and reproducible: the same /data folder and the same
inputs always give the same AED figures. Nothing is hardcoded — every weight,
multiplier and threshold comes from /data/multipliers.json, and every price
from the CSV files in /data. The folder is re-read on every call to
load_data(), so dropping or editing files in /data changes the next result.

How files in /data are recognised (by their columns / keys, not their names):
  * CSV with skill columns        -> merged into the skill index (later files
                                     override earlier ones on skill_id)
  * CSV with verified-offer cols  -> appended to the verified offers
  * CSV with date,skill_id,price  -> 30-day price history (sparklines)
  * JSON with pricing sections    -> merged into the multipliers
  * JSON {skill_id: [keywords]}   -> CV / JD keyword dictionary
Anything else is listed in the Data Room as "unrecognised" and ignored.

Run `python engine.py` for a printed self-test waterfall.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

_APP_DIR = Path(__file__).resolve().parent
# Normally ./data. If the data files were uploaded flat next to engine.py (e.g. via GitHub's web uploader,
# which can drop folder structure), fall back to the app folder so the app still starts.
DATA_DIR = _APP_DIR / "data"
if not DATA_DIR.is_dir() and (_APP_DIR / "skills_index.csv").is_file():
    DATA_DIR = _APP_DIR

SKILL_COLS = ["skill_id", "skill_name", "category", "base_monthly_aed", "pct_change_30d",
              "ai_replaceability_score", "demand_velocity", "sample_size"]
OFFER_COLS = ["role_title", "emirate", "years_exp", "education", "skills_list",
              "verified_monthly_aed", "source_type"]
HISTORY_COLS = ["date", "skill_id", "price_aed"]
MULTIPLIER_KEYS = {"bundle", "synergy", "experience_tiers", "location", "education",
                   "ai_adjustment", "comps", "bands", "rounding_aed"}
REQUIRED_MULTIPLIER_KEYS = ["bundle", "synergy", "experience_tiers", "location", "education",
                            "ai_adjustment", "comps", "bands", "rounding_aed"]
CANONICAL_ORDER = ["multipliers.json", "skills_index.csv", "verified_offers.csv",
                   "price_history.csv", "skill_keywords.json"]


class DataError(Exception):
    """Raised when /data cannot support a valuation (e.g. no multipliers file)."""


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------
@dataclass
class DataFile:
    name: str
    kind: str              # skills | offers | history | multipliers | keywords | unrecognised | error
    rows: int | None
    status: str            # active | ignored | error
    detail: str = ""
    size_bytes: int = 0
    modified: str = ""


@dataclass
class MarketData:
    skills: pd.DataFrame
    offers: pd.DataFrame
    history: pd.DataFrame
    multipliers: dict
    keywords: dict
    files: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    data_dir: Path = DATA_DIR

    # convenience lookups -------------------------------------------------------------
    def skill(self, skill_id: str) -> dict:
        row = self.skills.loc[self.skills["skill_id"] == skill_id]
        if row.empty:
            raise KeyError(skill_id)
        return row.iloc[0].to_dict()

    def skill_name(self, skill_id: str) -> str:
        try:
            return self.skill(skill_id)["skill_name"]
        except KeyError:
            return skill_id

    @property
    def emirates(self) -> list:
        return list(self.multipliers["location"]["factors"].keys())

    @property
    def education_levels(self) -> list:
        return list(self.multipliers["education"]["levels"].keys())

    @property
    def tier1_certs(self) -> list:
        return list(self.multipliers["education"].get("tier1_certs", []))

    @property
    def experience_tiers(self) -> list:
        return list(self.multipliers["experience_tiers"])


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", "_", str(c).strip().lower()) for c in df.columns]
    return df


def classify_columns(columns) -> tuple[str, list]:
    """Return (kind, missing_columns_for_closest_schema) for a CSV header."""
    cols = {re.sub(r"\s+", "_", str(c).strip().lower()) for c in columns}
    schemas = {"skills": SKILL_COLS, "offers": OFFER_COLS, "history": HISTORY_COLS}
    for kind, req in schemas.items():
        if set(req) <= cols:
            return kind, []
    best = min(schemas.items(), key=lambda kv: len(set(kv[1]) - cols))
    return "unrecognised", [c for c in best[1] if c not in cols]


def classify_json(obj) -> str:
    if isinstance(obj, dict) and MULTIPLIER_KEYS & set(obj.keys()):
        return "multipliers"
    if isinstance(obj, dict) and obj and all(
            isinstance(v, list) and all(isinstance(x, str) for x in v) for v in obj.values()):
        return "keywords"
    return "unrecognised"


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _file_sort_key(p: Path):
    try:
        return (0, CANONICAL_ORDER.index(p.name), p.name)
    except ValueError:
        return (1, 0, p.name.lower())


def load_data(data_dir: str | Path | None = None) -> MarketData:
    """Read every .csv / .json in /data and assemble the market dataset."""
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    if not data_dir.is_dir():
        raise DataError(f"Data folder not found: {data_dir}")

    files: list[DataFile] = []
    warnings: list[str] = []
    skill_frames, offer_frames, history_frames = [], [], []
    multipliers: dict = {}
    keywords: dict = {}

    paths = sorted([p for p in data_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".csv", ".json"} and not p.name.startswith(".")],
                   key=_file_sort_key)

    for p in paths:
        stat = p.stat()
        meta = dict(size_bytes=stat.st_size,
                    modified=dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"))
        try:
            if p.suffix.lower() == ".csv":
                df = _norm_cols(pd.read_csv(p))
                kind, missing = classify_columns(df.columns)
                if kind == "skills":
                    df["_source"] = p.name
                    skill_frames.append(df)
                elif kind == "offers":
                    df["_source"] = p.name
                    offer_frames.append(df)
                elif kind == "history":
                    history_frames.append(df)
                if kind == "unrecognised":
                    files.append(DataFile(p.name, kind, len(df), "ignored",
                                          "Missing columns: " + ", ".join(missing), **meta))
                else:
                    files.append(DataFile(p.name, kind, len(df), "active", **meta))
            else:
                obj = json.loads(p.read_text(encoding="utf-8"))
                kind = classify_json(obj)
                if kind == "multipliers":
                    multipliers = _deep_merge(multipliers, obj)
                    files.append(DataFile(p.name, kind, len(obj), "active",
                                          f"{len(obj)} sections", **meta))
                elif kind == "keywords":
                    for k, v in obj.items():
                        keywords.setdefault(k.strip().upper(), [])
                        keywords[k.strip().upper()] += [x.strip().lower() for x in v if x.strip()]
                    files.append(DataFile(p.name, kind, len(obj), "active",
                                          f"{sum(len(v) for v in obj.values())} keywords", **meta))
                else:
                    files.append(DataFile(p.name, kind, None, "ignored",
                                          "JSON not recognised as multipliers or keyword map", **meta))
        except Exception as exc:  # malformed file -> show in Data Room, keep going
            files.append(DataFile(p.name, "error", None, "error", str(exc)[:200], **meta))
            warnings.append(f"{p.name}: could not be read ({exc})")

    if not multipliers:
        raise DataError("No multipliers JSON found in /data — the pricing weights live in "
                        "/data/multipliers.json.")
    missing = [k for k in REQUIRED_MULTIPLIER_KEYS if k not in multipliers]
    if missing:
        raise DataError("multipliers.json is missing sections: " + ", ".join(missing))
    if not skill_frames:
        raise DataError("No skill index CSV found in /data (expected columns: " + ", ".join(SKILL_COLS) + ").")

    skills = _clean_skills(pd.concat(skill_frames, ignore_index=True), warnings)
    offers = (_clean_offers(pd.concat(offer_frames, ignore_index=True), skills, warnings)
              if offer_frames else pd.DataFrame(columns=OFFER_COLS + ["skill_ids", "_source"]))
    history = _clean_history(pd.concat(history_frames, ignore_index=True), warnings) \
        if history_frames else pd.DataFrame(columns=HISTORY_COLS)

    return MarketData(skills=skills, offers=offers, history=history, multipliers=multipliers,
                      keywords=keywords, files=files, warnings=warnings, data_dir=data_dir)


def _clean_skills(df: pd.DataFrame, warnings: list) -> pd.DataFrame:
    df = df.copy()
    df["skill_id"] = df["skill_id"].astype(str).str.strip().str.upper()
    df["skill_name"] = df["skill_name"].astype(str).str.strip()
    df["category"] = df["category"].astype(str).str.strip()
    for c in ["base_monthly_aed", "pct_change_30d", "ai_replaceability_score", "demand_velocity", "sample_size"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad = df[["base_monthly_aed", "ai_replaceability_score", "demand_velocity"]].isna().any(axis=1)
    if bad.any():
        warnings.append(f"Skill index: dropped {int(bad.sum())} row(s) with non-numeric prices/scores.")
        df = df[~bad]
    df["pct_change_30d"] = df["pct_change_30d"].fillna(0.0)
    df["sample_size"] = df["sample_size"].fillna(0).astype(int)
    out_of_range = (~df["ai_replaceability_score"].between(0, 100)).sum()
    if out_of_range:
        warnings.append(f"Skill index: {out_of_range} AI replaceability score(s) clamped to 0–100.")
    df["ai_replaceability_score"] = df["ai_replaceability_score"].clip(0, 100)
    dv_out = (~df["demand_velocity"].between(0.80, 1.30)).sum()
    if dv_out:
        warnings.append(f"Skill index: {dv_out} demand_velocity value(s) clamped to 0.80–1.30.")
    df["demand_velocity"] = df["demand_velocity"].clip(0.80, 1.30)
    dupes = df["skill_id"].duplicated(keep="last")
    if dupes.any():
        warnings.append(f"Skill index: {int(dupes.sum())} skill_id(s) overridden by a later file.")
        df = df[~dupes]
    return df.reset_index(drop=True)


def _resolver(skills: pd.DataFrame) -> dict:
    lut = {}
    for _, r in skills.iterrows():
        lut[r["skill_id"].lower()] = r["skill_id"]
        lut[r["skill_name"].lower()] = r["skill_id"]
    return lut


def _clean_offers(df: pd.DataFrame, skills: pd.DataFrame, warnings: list) -> pd.DataFrame:
    df = df.copy()
    df["years_exp"] = pd.to_numeric(df["years_exp"], errors="coerce")
    df["verified_monthly_aed"] = pd.to_numeric(df["verified_monthly_aed"], errors="coerce")
    bad = df[["years_exp", "verified_monthly_aed"]].isna().any(axis=1)
    if bad.any():
        warnings.append(f"Verified offers: dropped {int(bad.sum())} row(s) with non-numeric years or salary.")
        df = df[~bad]
    for c in ["role_title", "emirate", "education", "skills_list", "source_type"]:
        df[c] = df[c].fillna("").astype(str).str.strip()
    lut = _resolver(skills)
    unknown = set()

    def parse(s: str) -> list:
        ids = []
        for tok in re.split(r"[;|,]", s):
            t = tok.strip().lower()
            if not t:
                continue
            if t in lut:
                ids.append(lut[t])
            else:
                unknown.add(tok.strip())
        return ids

    df["skill_ids"] = df["skills_list"].apply(parse)
    if unknown:
        warnings.append("Verified offers reference skills not in the index (ignored for matching): "
                        + ", ".join(sorted(unknown)[:8]) + (" …" if len(unknown) > 8 else ""))
    return df.reset_index(drop=True)


def _clean_history(df: pd.DataFrame, warnings: list) -> pd.DataFrame:
    df = df.copy()
    df["skill_id"] = df["skill_id"].astype(str).str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price_aed"] = pd.to_numeric(df["price_aed"], errors="coerce")
    bad = df[["date", "price_aed"]].isna().any(axis=1)
    if bad.any():
        warnings.append(f"Price history: dropped {int(bad.sum())} malformed row(s).")
        df = df[~bad]
    return df.sort_values(["skill_id", "date"]).drop_duplicates(["skill_id", "date"], keep="last")


# --------------------------------------------------------------------------------------
# Primitive factors
# --------------------------------------------------------------------------------------
def round_aed(x: float, md: MarketData) -> int:
    step = md.multipliers.get("rounding_aed", 100)
    return int(math.floor(x / step + 0.5) * step)


def experience_tier(md: MarketData, years: float | None = None, tier_key: str | None = None) -> dict:
    tiers = md.experience_tiers
    if tier_key is not None:
        for t in tiers:
            if t["key"] == tier_key:
                return t
        raise ValueError(f"Unknown experience tier: {tier_key}")
    if years is None:
        raise ValueError("Provide years or tier_key")
    y = max(0, math.floor(float(years)))
    for t in tiers:
        hi = t.get("max_years")
        if y >= t["min_years"] and (hi is None or y <= hi):
            return t
    return tiers[-1] if y > tiers[-1]["min_years"] else tiers[0]


def location_factor(md: MarketData, emirate: str) -> float:
    factors = md.multipliers["location"]["factors"]
    if emirate not in factors:
        raise ValueError(f"Unknown emirate: {emirate}")
    return float(factors[emirate])


def education_factor(md: MarketData, level: str, certs: list | None = None) -> tuple[float, str]:
    edu = md.multipliers["education"]
    levels = edu["levels"]
    if level not in levels:
        raise ValueError(f"Unknown education level: {level}")
    base = float(levels[level])
    tier1 = {c.lower() for c in edu.get("tier1_certs", [])}
    held = [c for c in (certs or []) if c.lower() in tier1]
    m = base + (float(edu["tier1_cert_premium"]) if held else 0.0)
    m = min(m, float(edu["max_multiplier"]))
    detail = f"{level} {base:.2f}"
    if held:
        detail += f" + Tier-1 cert {edu['tier1_cert_premium']:+.2f} ({', '.join(held)})"
    if m < base + (float(edu["tier1_cert_premium"]) if held else 0.0) - 1e-9:
        detail += f" · capped at {edu['max_multiplier']:.2f}"
    return m, detail


def ai_adjustment(md: MarketData, score: float) -> float:
    a = md.multipliers["ai_adjustment"]
    raw = 1 + a["sensitivity"] * ((a["pivot_score"] - score) / a["pivot_score"])
    return max(a["floor"], min(a["ceiling"], raw))


def ai_tag(md: MarketData, factor: float) -> str:
    a = md.multipliers["ai_adjustment"]
    if factor > a["premium_above"]:
        return "AI Premium"
    if factor < a["discount_below"]:
        return "Automation Discount"
    return "Neutral"


# --------------------------------------------------------------------------------------
# Skill extraction (CV / job description)
# --------------------------------------------------------------------------------------
def _terms_for(md: MarketData, skill_id: str, skill_name: str) -> list:
    terms = {skill_name.lower()}
    # strip a trailing parenthetical so "Demand Planning (S&OP)" also matches "demand planning"
    terms.add(re.sub(r"\s*\(.*?\)\s*", " ", skill_name.lower()).strip())
    terms.update(md.keywords.get(skill_id, []))
    return sorted(t for t in terms if t)


def extract_skills(text: str, md: MarketData) -> list:
    """Match free text against the skill index + keyword map.

    Returns every matched skill, strongest match first:
    [{skill_id, skill_name, hits, terms}], ranked by keyword hits then index price.
    """
    if not text or not text.strip():
        return []
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    found = []
    for _, r in md.skills.iterrows():
        hits, matched = 0, []
        for term in _terms_for(md, r["skill_id"], r["skill_name"]):
            pat = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
            n = len(re.findall(pat, low))
            if n:
                hits += n
                matched.append(term)
        if hits:
            found.append({"skill_id": r["skill_id"], "skill_name": r["skill_name"], "hits": hits,
                          "terms": matched, "base_monthly_aed": r["base_monthly_aed"]})
    found.sort(key=lambda d: (-d["hits"], -d["base_monthly_aed"]))
    return found


def detect_years(text: str) -> int | None:
    """Best guess at years of experience stated in a CV ("5 years", "7+ yrs"). Largest plausible value wins."""
    if not text:
        return None
    vals = [int(n) for n in re.findall(r"(?<!\d)(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", text.lower())]
    vals = [v for v in vals if 0 < v <= 45]
    return max(vals) if vals else None


def detect_certs(text: str, md: MarketData) -> list:
    """Spot Tier-1 credentials mentioned in a CV (used to pre-fill the form)."""
    if not text:
        return []
    low = text.lower()
    out = []
    for c in md.tier1_certs:
        token = c.split("(")[0].strip().lower()
        if token in {"aws certified", "ml specialization"}:
            hit = token in low
        else:
            hit = re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", low) is not None
        if hit:
            out.append(c)
    return out


# --------------------------------------------------------------------------------------
# Comps
# --------------------------------------------------------------------------------------
def match_offers(md: MarketData, skill_ids: list, emirate: str, years: float | None) -> pd.DataFrame:
    cfg = md.multipliers["comps"]
    if md.offers.empty:
        return md.offers.iloc[0:0]
    df = md.offers.copy()
    wanted = set(skill_ids)
    df["skill_overlap"] = df["skill_ids"].apply(lambda ids: len(wanted & set(ids)))
    mask = df["skill_overlap"] >= int(cfg.get("min_skill_overlap", 1))
    if cfg.get("match_emirate", True):
        mask &= df["emirate"].str.lower() == emirate.lower()
    gap = cfg.get("max_years_gap")
    if gap is not None and years is not None:
        mask &= (df["years_exp"] - float(years)).abs() <= float(gap)
    return df[mask].sort_values(["skill_overlap", "verified_monthly_aed"], ascending=[False, False])


# --------------------------------------------------------------------------------------
# Core valuation
# --------------------------------------------------------------------------------------
def value_profile(md: MarketData, skill_ids: list, emirate: str, education: str,
                  years: float | None = None, tier_key: str | None = None,
                  certs: list | None = None) -> dict:
    """Price a skill bundle. Returns bands, factors and a step-by-step AED waterfall.

    skill_ids: in priority order; only the first `bundle.max_skills` are used.
    """
    m = md.multipliers
    max_n = int(m["bundle"].get("max_skills", 5))
    ids = []
    for s in skill_ids:
        s = str(s).strip().upper()
        if s not in ids and s in set(md.skills["skill_id"]):
            ids.append(s)
    ids = ids[:max_n]
    if not ids:
        raise ValueError("No recognised skills to value.")

    rows = [md.skill(s) for s in ids]
    rows.sort(key=lambda r: -r["base_monthly_aed"])

    # 1. Skill bundle base ------------------------------------------------------------
    raw_w = list(m["bundle"]["weights"])[:len(rows)]
    w_sum = sum(raw_w)
    weights = [w / w_sum for w in raw_w]
    composite = sum(w * r["base_monthly_aed"] for w, r in zip(weights, rows))
    syn = m["synergy"]
    primary_cat = rows[0]["category"]
    complementary = [r for r in rows[1:]
                     if r["category"] != primary_cat and r["ai_replaceability_score"] < syn.get("max_ai_score", 101)]
    synergy_pct = min(len(complementary) * syn["bonus_per_complementary_skill"], syn["cap"])
    bundle_base = composite * (1 + synergy_pct)

    # 2–5. Multipliers -----------------------------------------------------------------
    tier = experience_tier(md, years=years, tier_key=tier_key)
    m_exp = float(tier["multiplier"])
    m_loc = location_factor(md, emirate)
    m_edu, edu_detail = education_factor(md, education, certs)
    ai_score = sum(w * r["ai_replaceability_score"] for w, r in zip(weights, rows))
    a_ai = ai_adjustment(md, ai_score)
    tag = ai_tag(md, a_ai)
    dv = sum(w * r["demand_velocity"] for w, r in zip(weights, rows))

    # 6. Index median + comps blend -------------------------------------------------
    steps_raw = [composite]
    steps_raw.append(bundle_base)
    steps_raw.append(steps_raw[-1] * m_exp)
    steps_raw.append(steps_raw[-1] * m_loc)
    steps_raw.append(steps_raw[-1] * m_edu)
    steps_raw.append(steps_raw[-1] * a_ai)
    steps_raw.append(steps_raw[-1] * dv)
    p_index = steps_raw[-1]

    comp_years = years if years is not None else tier.get("rep_years")
    comps = match_offers(md, ids, emirate, comp_years)
    comps_median = float(statistics.median(comps["verified_monthly_aed"])) if len(comps) else None
    cfg = m["comps"]
    if comps_median is not None:
        p50_raw = cfg["index_weight"] * p_index + cfg["offers_weight"] * comps_median
    else:
        p50_raw = p_index
    steps_raw.append(p50_raw)

    labels = [
        ("Base Skill Composite", f"Σ wᵢ × base, {len(rows)} skill{'s' if len(rows) > 1 else ''}"),
        ("Skill Synergy Bonus", f"+{synergy_pct * 100:.0f}% · {len(complementary)} cross-domain"),
        ("Experience", f"× {m_exp:.2f} · {tier['label']}"),
        ("Emirate", f"× {m_loc:.2f} · {emirate}"),
        ("Credentials", f"× {m_edu:.2f} · {edu_detail}"),
        ("AI Adjustment", f"× {a_ai:.3f} · {tag} (S = {ai_score:.0f})"),
        ("Demand Velocity", f"× {dv:.3f}"),
        ("Verified Comps Blend",
         (f"{cfg['index_weight'] * 100:.0f}/{cfg['offers_weight'] * 100:.0f} with median of "
          f"{len(comps)} offer{'s' if len(comps) != 1 else ''} (AED {round_aed(comps_median, md):,})")
         if comps_median is not None else "No matching verified offers · index only"),
    ]
    rounded = [round_aed(v, md) for v in steps_raw]
    waterfall = []
    for i, ((step, note), r) in enumerate(zip(labels, rounded)):
        delta = r if i == 0 else r - rounded[i - 1]
        waterfall.append({"step": step, "note": note, "delta_aed": delta, "running_aed": r})

    bands_cfg = m["bands"]
    p50 = rounded[-1]
    bands = {"p25": round_aed(bands_cfg["p25"] * p50_raw, md),
             "p50": p50,
             "p75": round_aed(bands_cfg["p75"] * p50_raw, md)}

    skill_rows = []
    for w, r in zip(weights, rows):
        a_single = ai_adjustment(md, r["ai_replaceability_score"])
        skill_rows.append({
            "skill_id": r["skill_id"], "skill_name": r["skill_name"], "category": r["category"],
            "weight": w, "base_monthly_aed": r["base_monthly_aed"],
            "weighted_aed": w * r["base_monthly_aed"],
            "ai_replaceability_score": r["ai_replaceability_score"],
            "ai_tag": ai_tag(md, a_single), "demand_velocity": r["demand_velocity"],
            "pct_change_30d": r["pct_change_30d"], "sample_size": r["sample_size"],
            "complementary": r in complementary,
        })

    return {
        "inputs": {"skill_ids": ids, "emirate": emirate, "education": education,
                   "years": years, "tier_key": tier["key"], "certs": list(certs or [])},
        "skills": skill_rows,
        "composite_base": composite,
        "synergy_pct": synergy_pct,
        "bundle_base": bundle_base,
        "experience_tier": tier,
        "m_exp": m_exp, "m_loc": m_loc, "m_edu": m_edu, "edu_detail": edu_detail,
        "ai_score": ai_score, "a_ai": a_ai, "ai_tag": tag,
        "future_proof_score": round(100 - ai_score),
        "demand_velocity": dv,
        "p_index": p_index, "p_index_rounded": rounded[-2],
        "comps": comps, "comps_median": comps_median,
        "p50_raw": p50_raw,
        "bands": bands,
        "annual": {k: v * 12 for k, v in bands.items()},
        "waterfall": waterfall,
        "sample_size": int(sum(r["sample_size"] for r in rows)),
        "model_version": m.get("model_version", ""),
    }


def salary_position(md: MarketData, result: dict, current: float | None) -> dict | None:
    if not current or current <= 0:
        return None
    b = result["bands"]
    tol = md.multipliers.get("salary_position", {}).get("at_market_tolerance", 0.03)
    current = float(current)
    gap = round_aed(current - b["p50"], md)
    pct = (current - b["p50"]) / b["p50"]
    if current < b["p25"]:
        status, tone = "Significantly underpaid", "warn"
    elif pct < -tol:
        status, tone = "Below market", "warn"
    elif current > b["p75"]:
        status, tone = "Above top-decile band", "good"
    elif pct > tol:
        status, tone = "Above market median", "good"
    else:
        status, tone = "At market", "neutral"
    return {"current": current, "gap_monthly": gap, "gap_annual": gap * 12, "gap_pct": pct,
            "status": status, "tone": tone}


# --------------------------------------------------------------------------------------
# Market views
# --------------------------------------------------------------------------------------
def sparkline(md: MarketData, skill_id: str) -> list:
    """30-day price path. Uses price_history if present (rescaled so the last point equals
    today's index price), otherwise a straight line implied by pct_change_30d."""
    s = md.skill(skill_id)
    base = float(s["base_monthly_aed"])
    h = md.history[md.history["skill_id"] == skill_id] if not md.history.empty else md.history
    if len(h) >= 2:
        vals = h["price_aed"].astype(float).tolist()[-31:]
        scale = base / vals[-1] if vals[-1] else 1.0
        return [v * scale for v in vals]
    start = base / (1 + float(s["pct_change_30d"]) / 100)
    return [start + (base - start) * i / 30 for i in range(31)]


def market_table(md: MarketData) -> pd.DataFrame:
    df = md.skills.copy()
    df["ai_factor"] = df["ai_replaceability_score"].apply(lambda s: ai_adjustment(md, s))
    df["ai_tag"] = df["ai_factor"].apply(lambda a: ai_tag(md, a))
    df["sparkline"] = df["skill_id"].apply(lambda s: sparkline(md, s))
    return df


def category_exposure(md: MarketData) -> pd.DataFrame:
    """Sample-size-weighted AI exposure, price and 30-day trend per category/department."""
    df = md.skills.copy()
    df["w"] = df["sample_size"].clip(lower=1)
    for c in ["ai_replaceability_score", "pct_change_30d", "base_monthly_aed"]:
        df[c + "_w"] = df[c] * df["w"]
    g = df.groupby("category").agg(skills=("skill_id", "count"), w=("w", "sum"),
                                   sample_size=("sample_size", "sum"),
                                   ai_w=("ai_replaceability_score_w", "sum"),
                                   pct_w=("pct_change_30d_w", "sum"),
                                   base_w=("base_monthly_aed_w", "sum"))
    out = pd.DataFrame({"skills": g["skills"], "sample_size": g["sample_size"],
                        "avg_ai_score": g["ai_w"] / g["w"],
                        "avg_pct_change_30d": g["pct_w"] / g["w"],
                        "avg_base_aed": g["base_w"] / g["w"]})
    return out.reset_index().sort_values("avg_ai_score", ascending=False)


def upskill_scan(md: MarketData, profile: dict, candidate_ids: list | None = None) -> pd.DataFrame:
    """Value the profile with each candidate skill added; report the AED/month change."""
    base = value_profile(md, **profile)
    held = set(base["inputs"]["skill_ids"])
    pool = candidate_ids or [s for s in md.skills["skill_id"] if s not in held]
    rows = []
    for s in pool:
        if s in held:
            continue
        res = simulate_with(md, profile, [s])
        rows.append({"skill_id": s, "skill_name": md.skill_name(s),
                     "category": md.skill(s)["category"],
                     "new_p50": res["bands"]["p50"],
                     "delta_aed": res["bands"]["p50"] - base["bands"]["p50"],
                     "ai_tag": ai_tag(md, ai_adjustment(md, md.skill(s)["ai_replaceability_score"]))})
    return pd.DataFrame(rows).sort_values("delta_aed", ascending=False).reset_index(drop=True)


def simulate_with(md: MarketData, profile: dict, add_ids: list) -> dict:
    """Value a profile after adding skills. When the bundle exceeds the 5-skill cap the
    highest-priced skills are kept."""
    combined = list(dict.fromkeys(list(profile["skill_ids"]) + list(add_ids)))
    combined.sort(key=lambda s: -md.skill(s)["base_monthly_aed"])
    p = dict(profile)
    p["skill_ids"] = combined
    return value_profile(md, **p)


# --------------------------------------------------------------------------------------
# Negotiation brief
# --------------------------------------------------------------------------------------
def negotiation_brief(md: MarketData, result: dict, current: float | None = None,
                      role_label: str | None = None, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    b = result["bands"]
    cfg = md.multipliers.get("negotiation", {})
    anchor = b.get(cfg.get("anchor_band", "p75"), b["p75"])
    mix = float(cfg.get("target_mix_p50_to_p75", 0.5))
    target = round_aed(b["p50"] + mix * (b["p75"] - b["p50"]), md)
    floor = b.get(cfg.get("floor_band", "p50"), b["p50"])
    pos = salary_position(md, result, current)
    inp = result["inputs"]
    tier = result["experience_tier"]["label"]
    certs = ", ".join(inp["certs"]) if inp["certs"] else "none listed"
    skills = result["skills"]
    f = lambda x: f"AED {x:,.0f}"

    lines = [
        "# Qimah Negotiation Brief",
        f"*Generated {today:%d %b %Y} · model {result['model_version']} · figures in AED/month*",
        "",
        "## 1. Profile priced",
        f"- **Role / bundle:** {role_label or ', '.join(s['skill_name'] for s in skills)}",
        f"- **Emirate:** {inp['emirate']} · **Experience:** {tier} · **Education:** {inp['education']} · **Tier-1 credentials:** {certs}",
        "",
        "## 2. Market position",
        f"- P25 conservative: **{f(b['p25'])}** · P50 fair market value: **{f(b['p50'])}** · P75 top-decile: **{f(b['p75'])}**",
    ]
    if pos:
        sign = "+" if pos["gap_monthly"] >= 0 else "−"
        lines.append(f"- Current / offered: **{f(pos['current'])}** → {pos['status']} "
                     f"({sign}{f(abs(pos['gap_monthly']))}/mo vs P50, {sign}{f(abs(pos['gap_annual']))}/yr)")
    lines += [
        "",
        "## 3. Recommended ask",
        f"- **Opening anchor:** {f(anchor)}/mo",
        f"- **Target settlement:** {f(target)}/mo",
        f"- **Walk-away floor:** {f(floor)}/mo",
    ]
    if pos and pos["current"] >= b["p75"]:
        lines.append("- You are already at or above the top band — negotiate on scope, title, bonus or "
                     "equity rather than base pay.")
    lines += ["", "## 4. Evidence to cite"]
    top = skills[0]
    lines.append(f"- Primary skill **{top['skill_name']}** indexes at {f(top['base_monthly_aed'])}/mo at junior baseline, "
                 f"{top['pct_change_30d']:+.1f}% over 30 days (n = {top['sample_size']}).")
    rising = [s for s in skills if s["pct_change_30d"] > 0]
    if len(rising) > 1:
        lines.append("- Rising skills in your bundle: " + ", ".join(
            f"{s['skill_name']} ({s['pct_change_30d']:+.1f}%)" for s in rising) + ".")
    if result["ai_tag"] == "AI Premium":
        lines.append(f"- Bundle carries an **AI Premium** (replaceability {result['ai_score']:.0f}/100, "
                     f"factor ×{result['a_ai']:.3f}) — your work is hard to automate.")
    elif result["ai_tag"] == "Automation Discount":
        lines.append(f"- Bundle carries an **Automation Discount** (replaceability {result['ai_score']:.0f}/100). "
                     "Lead with judgement-heavy outcomes rather than routine tasks.")
    if result["synergy_pct"] > 0:
        lines.append(f"- Cross-domain synergy adds +{result['synergy_pct'] * 100:.0f}% — few candidates combine these areas.")
    if result["demand_velocity"] > 1.0:
        lines.append(f"- Demand velocity ×{result['demand_velocity']:.2f}: hiring demand currently outpaces supply.")
    if result["comps_median"] is not None:
        lines.append(f"- {len(result['comps'])} verified UAE offer(s) for similar profiles in {inp['emirate']} "
                     f"have a median of {f(round_aed(result['comps_median'], md))}/mo.")
    lines += [
        "",
        "## 5. Talking points",
        f"1. \"Based on current UAE market data for {top['skill_name']} at my level in {inp['emirate']}, "
        f"the fair market range is {f(b['p25'])}–{f(b['p75'])} a month.\"",
        f"2. \"Given my {tier.split('(')[0].strip()} experience and credentials, I'm looking for {f(anchor)}.\"",
        f"3. If they push back: \"I can be flexible towards {f(target)} if we agree a review at six months.\"",
        "",
        "---",
        f"*Method: skill composite × experience × emirate × credentials × AI adjustment × demand velocity"
        f"{', blended 75/25 with verified offers' if result['comps_median'] is not None else ''}. "
        f"Index sample: {result['sample_size']:,} data points. Not financial or legal advice.*",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    md = load_data()
    print(f"Loaded {len(md.skills)} skills, {len(md.offers)} offers, {len(md.history)} history rows")
    for f_ in md.files:
        print(f"  {f_.name:<24} {f_.kind:<13} rows={f_.rows} {f_.status} {f_.detail}")
    cv = ("Data scientist with 5 years experience in machine learning, PyTorch and MLOps on AWS. "
          "Built ETL pipelines in Airflow and Spark. Financial modelling and DCF valuation for M&A "
          "due diligence. CFA Level II.")
    found = extract_skills(cv, md)
    print("\nExtracted:", [(d["skill_id"], d["hits"]) for d in found])
    res = value_profile(md, [d["skill_id"] for d in found], emirate="Dubai",
                        education="Master's / MBA", years=5, certs=detect_certs(cv, md))
    print(f"\nWaterfall ({res['ai_tag']}, future-proof {res['future_proof_score']}/100):")
    for s in res["waterfall"]:
        print(f"  {s['step']:<22} {s['delta_aed']:>+9,}  → {s['running_aed']:>8,}   {s['note']}")
    print("Bands:", res["bands"])
    print("\n" + negotiation_brief(md, res, current=26000))
