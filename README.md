# Qimah (قيمة) — UAE Skill Pricing & Compensation Engine (prototype)

All figures are AED/month, rounded to the nearest AED 100. Nothing is scraped and nothing is hardcoded:
`engine.py` re-reads `./data` on every interaction.

## Run (macOS)
```bash
cd ~/Desktop/Qimah_Prototype
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
streamlit run app.py
```
Engine self-test without the UI: `python engine.py`

## /data
| File | What it holds |
|---|---|
| `skills_index.csv` | 20 indexed skills: `skill_id, skill_name, category, base_monthly_aed, pct_change_30d, ai_replaceability_score, demand_velocity, sample_size` |
| `multipliers.json` | Every weight in the model: bundle weights, synergy, experience tiers, emirate factors, education/cert premium, AI adjustment, comps blend, bands, rounding, negotiation anchors |
| `verified_offers.csv` | 10 anonymized offers: `role_title, emirate, years_exp, education, skills_list (; separated), verified_monthly_aed, source_type` |
| `skill_keywords.json` | `{skill_id: [keywords]}` used to pull skills out of CVs and job descriptions |
| `price_history.csv` | `date, skill_id, price_aed` — 30-day series behind the ticker sparklines |

Files are recognised by their **columns/keys, not their names**, so you can drop in extra files:
- another skills CSV → new skills are added, matching `skill_id`s are overridden
- another offers CSV → rows are added to the comps pool
- a JSON with any multiplier section (e.g. `{"bands": {"p75": 1.20}}`) → merged over `multipliers.json`
- anything unrecognised or malformed is listed in the Data Room and ignored

## Model
P_index = B × M_exp × M_loc × M_edu × A_AI × demand_velocity, where B is the weighted top-5 skill composite
(0.45/0.25/0.15/0.10/0.05, normalized) plus a +4% synergy bonus per complementary cross-domain skill (cap +12%), and
A_AI = 1 + 0.18 × (45 − S)/45 clamped to [0.82, 1.18]. When offers match (same emirate, ≥1 shared skill,
±3 yrs experience — `comps.max_years_gap`, set to `null` to drop the seniority filter), P50 = 75% P_index + 25% median offer.
P25 = 0.88 × P50, P75 = 1.16 × P50.

## Public demo mode
Create an empty `READ_ONLY` file next to `app.py` (or set `QIMAH_READ_ONLY=1`) to switch off Data Room uploads on a
hosted copy, where all visitors share one `/data` folder. Reload still works; local runs stay editable.
