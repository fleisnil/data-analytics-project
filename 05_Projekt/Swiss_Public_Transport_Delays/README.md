# Swiss Public Transport Delay Analytics

## Research question

**Which factors are associated with public transport delays in Switzerland, and how do these effects differ between regions, transport modes and time periods?**

This repository is a reproducible Data Analytics project for the ZHAW module. It is designed to meet every minimum requirement and to provide evidence for all six additional criteria. The project studies associations, not causal effects.

## Study design

The unit of analysis is a vehicle call at a Swiss public-transport stop. The main outcome is delay in minutes, calculated from scheduled and observed/forecast arrival or departure times. The main explanatory dimensions are:

- official Swiss large region assigned to the station panel;
- transport mode and operator;
- hour, day of week, weekend and peak/off-peak period;
- hourly precipitation, snowfall, wind and temperature;
- station and route context.

The main analytical model is a regression with explicit group comparisons and interactions. A random-forest model supplies out-of-sample predictive evaluation and permutation importance. ANOVA, chi-squared and correlation tests include p-values. Station profiles are additionally grouped with k-means.

## Data sources

1. **Swiss public transport API (`transport.opendata.ch`)**: JSON stationboard and location endpoints. Repeated group-owned snapshots supply scheduled calls, prognosis, delay, mode, operator and coordinates. This is the recommended primary source because it satisfies the API requirement without requiring multi-gigabyte daily downloads.
2. **Open-Meteo Historical/Forecast API**: hourly weather at each selected station coordinate. Weather is joined to transport observations by station and local hour.
3. **Open Data Platform Mobility Switzerland – Actual data v2**: the web scraper discovers official daily files for validation or a selected historical extension. One current daily file is about 670 MB, so a 28-day full-file design should be approved before the group commits to it.

Important limitation: the official actual-data publisher states that many values are the last available forecast rather than a measured door-event time, and journeys without real-time information may be absent. The project therefore uses the term *reported delay* and avoids causal claims.

## Repository structure

```text
config/             Study settings and station panel
data/               Raw, interim and processed data (ignored by Git)
database/           Generated SQLite database (ignored by Git)
docs/               Method, integration audit, AI log and data dictionary
notebooks/          Submission-facing Jupyter notebooks
presentation/       Concept and final slide sources plus points appendix
reports/            Generated figures and tables (ignored by Git)
scripts/            Convenience commands
sql/                Documented SQLite and PostgreSQL queries
src/sptdelays/      Reusable Python package
tests/              Automated checks for critical transformations
artifacts/          Final Moodle ZIP/PDF/video files (ignored by Git)
```

## Quick start in VS Code

Install [uv](https://docs.astral.sh/uv/) or use a normal Python virtual environment.

```powershell
uv venv
uv sync --extra dev
uv run sptdelays resolve-stations
uv run sptdelays collect-live
uv run sptdelays prepare --source live
uv run sptdelays collect-weather
uv run sptdelays integrate
uv run sptdelays sqlite
uv run sptdelays duckdb
uv run sptdelays analyse
uv run sptdelays model
uv run sptdelays cluster
uv run sptdelays map
uv run pytest
```

The same sequence is available as:

```powershell
uv run python scripts/run_demo_pipeline.py
```

The demo uses live stationboards. It proves the workflow, but a single snapshot is not sufficient for the final claims.

## Recommended final collection

For the final submission, collect at least **28 service days**, including weekdays and weekends. Run one live snapshot every 15–30 minutes. Each successful call writes immutable raw JSON, appends observations and updates `collection_log.csv`:

```powershell
uv run sptdelays collect-live
uv run sptdelays status

# Example collection window: 24 hours at 20-minute intervals
powershell -ExecutionPolicy Bypass -File scripts/run_collection_loop.ps1 -IntervalMinutes 20 -Iterations 72
```

After the approved collection period:

```powershell
uv run sptdelays prepare --source live
uv run sptdelays collect-weather
uv run sptdelays integrate
uv run sptdelays sqlite
uv run sptdelays duckdb
uv run sptdelays analyse
uv run sptdelays model
uv run sptdelays cluster
uv run sptdelays map
```

The Actual data v2 collector remains available for a selected validation date or an approved historical design:

```powershell
uv run sptdelays list-actuals
uv run sptdelays collect-actuals --dates YYYY-MM-DD
```

See `docs/COLLECTION_PLAN.md` before starting the final collection.

## Modeling and interpretation

The pipeline produces two complementary models:

1. **OLS association model** on `log1p(delay_minutes)` with robust HC3 standard errors, region/mode/time terms, weather variables and selected interactions. Coefficients and p-values are used for careful association statements.
2. **Random-forest regression** with a chronological holdout where multiple dates exist. Performance is compared with a mean baseline using RMSE, MAE and R². Metrics are also reported by region and transport mode.

Do not interpret a statistically significant coefficient as a causal effect. Weather is reanalysis/forecast-grid data, real-time coverage is selective, and congestion, incidents and vehicle rotations can be unobserved confounders.

## Database requirement

`sptdelays sqlite` creates `database/sptdelays.sqlite` and runs SQL queries from Python. It stores normalized station, weather and transport tables, creates indexes and exports SQL aggregation results to `reports/tables/`.

## PostgreSQL bonus

`sptdelays duckdb` creates a persistent non-SQLite analytical database and executes a documented SQL join plus aggregations from Python. This provides an immediately reproducible implementation of the rubric's “PostgreSQL or similar” criterion. Confirm with the lecturer that DuckDB is accepted as similar.

For a full PostgreSQL implementation:

```powershell
Copy-Item .env.example .env
docker compose up -d
uv run sptdelays postgres
```

The PostgreSQL loader uses SQLAlchemy/psycopg and runs joins and aggregations from Python. Credentials stay in `.env`, which is ignored by Git.

## Evidence for the 22-point rubric

| Criterion | Evidence |
|---|---|
| API/web collection | `collect_actuals.py`, `collect_live.py`, `collect_weather.py` |
| Two-source integration | `prepare.py`, generated `integration_audit.csv` |
| SQLite and SQL from Python | `database.py`, `sql/sqlite_analysis.sql` |
| Rich EDA | `eda.py`, Notebook 03, generated figures/tables |
| Regression/group comparison | `modeling.py`, Notebook 04 |
| Model evaluation | overall and subgroup RMSE, MAE and R² tables |
| Interpretation | Notebook 04 and presentation discussion slides |
| AI reflection | `docs/AI_USAGE_LOG.md` and presentation section |
| Moodle materials | submission checklist in `docs/SUBMISSION_CHECKLIST.md` |
| Creativity | official data streaming, weather integration, propagation indicators |
| PostgreSQL or similar | validated DuckDB SQL join; Docker Compose and PostgreSQL loader also included |
| Geodata | station coordinates and interactive Folium map |
| Tests with p-values | ANOVA, chi-squared and Spearman results |
| k-means | `clustering.py`, station profile clusters and silhouette selection |
| Public GitHub | repository-ready structure; publish only after group review |
| Video presentation | complete slide source and timed speaking plan |

## GitHub workflow

Review the repository for personal data and large files before publishing. Then:

```powershell
git init
git add .
git commit -m "Initial reproducible delay analysis project"
git branch -M main
git remote add origin https://github.com/ORGANISATION/REPOSITORY.git
git push -u origin main
```

Do not commit `.env`, the SQLite database or large raw data. For reproducibility, document the collection dates and publish a small anonymized processed sample only if the data licence permits it.

## Moodle package

After final review, build the materials archive with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_submission.ps1 -GroupNumber 1
```

The script creates `artifacts/materials_group_01.zip`. Add the separately exported final PDF and recorded MP4 to `artifacts/`, then complete `docs/SUBMISSION_CHECKLIST.md` before upload.

## What still requires the group

- Lecturer approval of the concept.
- A multi-week final data collection window.
- Validation of station IDs and regional coverage.
- Group-owned interpretation and spoken explanation.
- Continuous, truthful AI-use logging.
- Final screenshots and generated numbers in the points appendix.
- Upload by one student using the correct group number.

The code cannot guarantee a grade. The final grade depends on data quality, correct interpretation, presentation delivery and the lecturer's evaluation.
