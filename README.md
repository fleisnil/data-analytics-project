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
2. **Open-Meteo Historical/Forecast API**: hourly weather at each selected station coordinate. Weather is joined to transport observations by station and scheduled UTC hour; local time is retained for calendar analysis. Archive and recent forecast values have different provenance.
3. **Open Data Platform Mobility Switzerland – Actual data v2**: the web scraper discovers official daily files for validation or a selected historical extension. One current daily file is about 670 MB, so a 28-day full-file design should be approved before the group commits to it.

Important limitation: the official actual-data publisher states that many values are the last available forecast rather than a measured door-event time, and journeys without real-time information may be absent. The project therefore uses the term *reported delay* and avoids causal claims.

## Repository structure

```text
config/             Study settings and station panel
data/               Raw, interim and processed data (ignored by Git)
database/           Generated SQLite and DuckDB databases (ignored by Git)
docs/               Method, integration audit, AI log and data dictionary
notebooks/          Submission-facing Jupyter notebooks
presentation/       Optimized editable concept deck, final slide outline and points appendix
reports/            Generated figures and tables (ignored by Git)
scripts/            Convenience commands
sql/                Documented SQLite, DuckDB and PostgreSQL queries
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
uv run sptdelays validate
uv run pytest -p no:cacheprovider
```

The saved-data development rebuild is also available as:

```powershell
uv run python scripts/run_demo_pipeline.py
```

This demo reads saved inputs by default. Use `--collect` only when a fresh API snapshot and weather download are intended. If you already have transport and weather inputs, rebuild **without network requests** using `uv run sptdelays pipeline --source live`. This writes `reports/tables/run_manifest.json` with input/code hashes, package versions, step status and dataset hash. It refreshes generated results, so archive an earlier run if it is needed for comparison. Run `uv run sptdelays status` to inspect collection gaps and `uv run sptdelays validate` for structural and coverage checks.

With the existing Windows `.venv`, the equivalent VS Code terminal command is `.\.venv\Scripts\sptdelays.exe pipeline --source live` after opening this repository folder directly. `.\.venv\Scripts\python.exe scripts/check_notebooks.py --execute` verifies all four notebooks against saved inputs.

## Recommended final collection

For the final submission, collect at least **28 service days**, including weekdays and weekends. Run one live snapshot every 15–30 minutes. Each successful call writes immutable raw JSON and one normalized CSV in `data/interim/live_snapshots/`, then updates `collection_log.csv`. Collection does not repeatedly rewrite the full observation history. The earlier `live_observations.csv` remains a read-only legacy input; preparation combines it with the new snapshot files:

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
uv run sptdelays validate
```

Once the transport and weather files are collected, the offline `pipeline` command runs that analysis sequence and records provenance. Data status `development` means the rows passed structural checks but study coverage targets remain unmet. A clean audit alone does not make results representative or complete the submission. The configurable 28 service days and 95% complete weather are project design targets, not minimums stated by the lecturer.

The Actual data v2 collector remains available for a selected validation date or an approved historical design:

```powershell
uv run sptdelays list-actuals
uv run sptdelays collect-actuals --dates YYYY-MM-DD
```

See `docs/COLLECTION_PLAN.md` before starting the final collection.

## Modeling and interpretation

The pipeline produces two complementary models:

1. **OLS association model** on `log1p(delay_minutes)` using complete weather cases. Station-clustered standard errors are used when possible; the model specification flags fewer than 30 clusters and other dependence that remains. Region/mode/time terms and a supported region-by-mode interaction address comparisons. `exp(coefficient)` describes a ratio of fitted geometric means of `delay + 1`, not a direct change in mean delay minutes.
2. **Random-forest regression** predicts raw delay minutes. Train and test are split chronologically by full service date when possible; preprocessing is fitted only on training rows. Performance is compared with both the overall *training* mean and a stronger region/mode/period training-group mean (at least ten training rows per group, otherwise the overall training mean) using RMSE, MAE and R². Subgroup metrics cover region, mode and time period. `holdout_coverage.csv` reports categories and stations in the test period that were unseen in training; such rows need caution when interpreting performance. A one-day holdout is explicitly a development check.

Do not interpret a statistically significant coefficient as a causal effect. Weather is reanalysis/forecast-grid data, real-time coverage is selective, and congestion, incidents and vehicle rotations can be unobserved confounders. Repeated calls share stations, journeys and days. The forest is a retrospective association benchmark using concurrent weather, not a real-time service forecast.

## Database requirement

`sptdelays sqlite` creates `database/sptdelays.sqlite` and runs SQL queries from Python. It stores normalized station, weather and transport tables, validates one-to-many keys and joins, creates indexes and exports SQL aggregation and row-count audit results to `reports/tables/`. SQLite and DuckDB now read the same integrated population. Failed validation preserves the previous database.

## PostgreSQL bonus

`sptdelays duckdb` creates a persistent non-SQLite analytical database and executes a documented SQL join plus aggregations from Python. This is evidence for the rubric's “PostgreSQL or similar” criterion, but the lecturer must confirm DuckDB is accepted as similar.

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
| Two-source integration | `prepare.py`, generated `preparation_audit.csv`, `integration_audit.csv` and unmatched-key file |
| SQLite and SQL from Python | `database.py`, `sql/sqlite_analysis.sql` |
| Rich EDA | `eda.py`, Notebook 03, generated figures/tables, including zero-observation region-days |
| Regression/group comparison | `modeling.py`, Notebook 04 |
| Model evaluation | chronological split, overall and subgroup RMSE, MAE and R² tables, overall and group-mean training baselines |
| Interpretation | Notebook 04 and presentation discussion slides |
| AI reflection | `docs/AI_USAGE_LOG.md` and presentation section |
| Moodle materials | submission checklist in `docs/SUBMISSION_CHECKLIST.md` |
| Creativity | group-collected stationboard snapshots, explicit forecast timing, station-level weather and regional/mode/time comparison |
| PostgreSQL or similar | validated DuckDB SQL join; Docker Compose and PostgreSQL loader also included |
| Geodata | station coordinates and interactive Folium map |
| Tests with p-values | ANOVA, chi-squared and Spearman results |
| k-means | `clustering.py`, station profile clusters and silhouette selection |
| Public GitHub | project files at the repository root on branch `colin`; generated datasets and credentials remain excluded |
| Video presentation | complete slide source and timed speaking plan |

## GitHub workflow

This project is stored directly at the root of [`fleisnil/data-analytics-project`](https://github.com/fleisnil/data-analytics-project) on branch `colin`. To continue work in a fresh checkout:

```powershell
git clone --branch colin https://github.com/fleisnil/data-analytics-project.git
cd data-analytics-project
uv sync --extra dev
```

Do not commit `.env`, the SQLite database or large raw data. These are deliberately ignored by Git and must be transferred separately for the final Moodle materials. For reproducibility, document the collection dates and publish a small anonymized processed sample only if the data licence permits it.

## Moodle package

After final review, build the materials archive with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_submission.ps1 -GroupNumber 1
```

First check the contents without building an archive: `powershell -ExecutionPolicy Bypass -File scripts/build_submission.ps1 -GroupNumber 1 -ValidateOnly`. Then run the command above. It creates `artifacts/materials_group_01.zip` and includes a hashed submission manifest. Add the separately exported final PDF and recorded MP4 to `artifacts/`, then complete `docs/SUBMISSION_CHECKLIST.md` before upload. Do not submit the current one-day development outputs as final results.

## What still requires the group

- Lecturer approval of the concept.
- A multi-week final data collection window.
- Validation of station IDs and regional coverage.
- Group-owned interpretation and spoken explanation.
- Continuous, truthful AI-use logging.
- Final screenshots and generated numbers in the points appendix.
- Upload by one student using the correct group number.

The code cannot guarantee a grade. The final grade depends on data quality, correct interpretation, presentation delivery and the lecturer's evaluation.
