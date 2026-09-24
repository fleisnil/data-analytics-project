---
marp: true
theme: default
paginate: true
---

# Swiss Public Transport Delays

## Project concept

Group XX · Full names · ZHAW Data Analytics

---

# Background and problem

- Reliable public transport is essential for work, education and connections.
- Delays vary over place, mode and time.
- Weather may matter, but operational and regional structures differ.
- Publicly available real-time and historical data make a reproducible analysis possible.

---

# Research question

**Which factors are associated with public transport delays in Switzerland, and how do these effects differ between regions, transport modes and time periods?**

Subquestions:

1. How do delay distributions differ by region, mode and period?
2. Are precipitation, snowfall and wind associated with reported delay?
3. Do mode differences vary across the sampled regions after adjusting for observed weather and time?

---

# Data sources

1. Swiss public transport JSON API: repeated stationboard snapshots, delays, mode, operator and coordinates.
2. Open-Meteo API: hourly weather by station coordinate.
3. Actual data v2: web-scraped resource links for validation or a selected historical extension.

Planned period: at least 28 service days.

---

# Data integration

1. Normalize BPUIC station identifiers.
2. Join station panel using `station_id`.
3. Derive delay and local time variables.
4. Join weather using normalized `station_id + scheduled UTC hour`.
5. Document matches, duplicates and every row loss.

---

# Methods

- Graphical and non-graphical EDA.
- ANOVA, chi-squared and Spearman tests with p-values and effect sizes.
- OLS association model with region/mode/time terms and interactions.
- Random-forest regression with chronological holdout and baseline comparison.
- k-means clustering of station delay profiles.
- Interactive map of station-level delay measures.

---

# Expected contribution

- A comparison across selected stations in all seven large regions rather than a single-route prediction.
- Transparent separation of association and causality.
- Reproducible API collection, SQLite, DuckDB and optional PostgreSQL code.
- Practical identification of where and when reported delays are concentrated.

---

# Risks and mitigation

- Last forecasts may replace true event times → preserve status and use careful wording.
- Real-time coverage may be selective → analyze missingness by operator/mode.
- Large Actual data files → API snapshots as the primary design.
- Repeated calls/journeys → stable keys, last report and snapshot-count audit.
- Weather grid mismatch → use station coordinates and disclose spatial resolution.

---

# Project plan

| Phase | Output |
|---|---|
| Collection | Raw transport, station and weather data |
| Preparation | Clean integrated analytical dataset and audit |
| EDA/tests | Figures, tables, p-values and effect sizes |
| Models | Holdout metrics, interactions and importance |
| Communication | GitHub, PDF slides, video and evidence appendix |
