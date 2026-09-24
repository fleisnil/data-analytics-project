---
marp: true
theme: default
paginate: true
---

# Swiss Public Transport Delays

Full names · Group XX · ZHAW Data Analytics

---

# Outline

1. Problem and research question
2. Data and integration
3. Exploratory findings
4. Statistical tests and models
5. Regional, mode and time differences
6. Conclusions, limitations and AI reflection

---

# Research question

**Which factors are associated with public transport delays in Switzerland, and how do these effects differ between regions, transport modes and time periods?**

State hypotheses before showing results.

---

# Data collection

- Swiss transport API snapshots: **[insert dates, interval and rows]**
- Open-Meteo: hourly weather
- Actual data v2 web scraper: **[insert validation evidence if used]**
- Unit: one reported vehicle call at a selected station

Insert a data-flow diagram and source citations.

---

# Preparation and integration

- Show exact join keys.
- Explain why UTC hour keys preserve the repeated autumn hour.
- Insert `preparation_audit.csv` and `integration_audit.csv`.
- State raw rows, duplicates, losses, weather match rate and final rows.
- Explain status values and the actual/last-forecast limitation.

---

# Exploratory analysis

Insert:

- delay distribution;
- mode comparison;
- region comparison;
- mode-by-time heatmap;
- interactive-map screenshot.

Describe patterns before explaining possible reasons.

---

# Statistical evidence

Insert selected rows from `statistical_tests.csv`:

- exact statistic and p-value;
- Holm-adjusted p-value and any sparse-cell warning;
- effect size;
- practical interpretation;
- note that significance does not prove causality.

---

# Regression design and evaluation

- OLS on `log1p(delay_minutes)` for exploratory conditional associations; explain the `delay + 1` coefficient scale.
- Random forest for out-of-sample evaluation.
- Chronological holdout and training-mean baseline; show train and test dates.
- Metrics: RMSE, MAE and R² overall and by subgroup.

Insert `model_metrics.csv`.

---

# What differs across groups?

Present only well-supported comparisons:

- region-by-mode interactions only when the design matrix supports them;
- peak versus off-peak;
- weather terms with confidence intervals;
- subgroup model performance.

Avoid league tables without uncertainty or coverage context.

---

# Station clusters and geography

- Explain standardized station-profile features.
- Report selected k and silhouette score.
- Show cluster plot and map.
- Interpret clusters as descriptive profiles, not natural or permanent categories.

---

# Conclusions

Answer the research question directly in three to five evidence-based statements.

Separate:

1. observed patterns;
2. model associations;
3. practical implications;
4. what cannot be concluded.

---

# Limitations

- actual versus last forecast;
- selective real-time coverage;
- station-panel representativeness;
- weather-grid resolution;
- unobserved incidents and network dependence;
- observational study: no causal conclusions.

---

# Reflection on AI usage

- Tools and tasks
- What improved speed or quality
- One concrete failure or unsupported suggestion
- How the group tested and corrected it
- What every group member understands and can explain

Use entries from `docs/AI_USAGE_LOG.md`.

---

# Reproducibility and material

- Public GitHub URL: **[insert after publication]**
- Python package, notebooks and tests
- Raw/processed-data policy and collection dates
- SQLite and DuckDB with join audits; PostgreSQL only if run and validated
- Complete material in Moodle ZIP

---

# Appendix: claimed points

Insert the completed evidence matrix from `points_appendix.md`, followed by readable screenshots and short code excerpts.
