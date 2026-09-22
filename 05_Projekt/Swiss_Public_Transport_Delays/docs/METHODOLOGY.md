# Methodology

## Research objective

The project estimates which observable factors are associated with reported public-transport delay and tests whether the associations differ across Swiss regions, transport modes and time periods.

The word **associated** is deliberate. The data are observational. The analysis does not identify causal effects.

## Research hypotheses

1. Reported delays differ across transport modes.
2. Reported delays differ across the seven Swiss large regions represented in the station panel.
3. Peak periods have a different delay distribution from off-peak periods.
4. Precipitation, snowfall and wind are positively associated with reported delays.
5. Region-by-mode differences remain after adjusting for weather and time variables.

## Unit of analysis

One row represents one reported vehicle call at a selected station and scheduled time. Repeated collector snapshots are deduplicated with a stable observation key.

## Outcome variables

- `delay_minutes_signed`: reported time minus scheduled time; negative values indicate early running.
- `delay_minutes`: signed delay clipped at zero for the main regression.
- `is_delayed_5`: 1 when delay is at least five minutes, otherwise 0.

The five-minute threshold is a transparent project definition, not an official universal Swiss punctuality threshold.

## Sources and collection

### Live stationboard API

The recommended primary source is the JSON API at `transport.opendata.ch`. The group collects repeated stationboard snapshots every 15–30 minutes over at least 28 service days. The API returns scheduled stops, prognosis times, delay, transport category, operator and station coordinates. Stable keys collapse repeated snapshots to the latest available prognosis for each vehicle call.

Source and documentation: https://transport.opendata.ch/docs.html

### Actual data v2

The official Actual data v2 page supplies daily CSV files. A Python scraper discovers the resource links and a streaming collector can retain the selected station panel. This source supports a selected historical validation or an alternative design approved by the lecturer. A current daily file is about 670 MB, which makes a full 28-day download unnecessarily heavy for the primary design.

Source: https://data.opentransportdata.swiss/en/dataset/ist-daten-v2

### Weather

Open-Meteo provides hourly temperature, precipitation, snowfall, wind speed and wind gusts for each station coordinate. Recent observations use the forecast endpoint when necessary; older dates use the historical archive endpoint.

Source: https://open-meteo.com/en/docs/historical-weather-api

## Station panel and regional comparison

The panel deliberately includes rail hubs and urban stops in all seven Swiss large regions. Station identifiers and coordinates are resolved through the locations API. The configured canton-to-region assignment follows the official Swiss large-region concept, which is consistent with NUTS 2.

The panel is a stratified analytical sample. It is not a census of every stop and should not be used to rank whole regions without discussing coverage.

## Preparation

1. Normalize seven- and nine-digit BPUIC identifiers.
2. Select arrival times where scheduled and reported arrival are both available; otherwise use departure.
3. Parse times in the Europe/Zurich timezone and convert them to UTC for calculation.
4. Calculate signed delay and a non-negative modeling target.
5. Remove duplicate observation keys.
6. Exclude missing targets, unmatched station-panel rows and delays above the documented plausibility limit of 180 minutes.
7. Add hour, weekday, weekend, peak period and broader day-period variables.
8. Join station metadata many-to-one on `station_id`.
9. Join weather many-to-one on `station_id + observation_hour`.

The generated audit tables record every row count and the weather match rate.

## EDA and statistical testing

EDA includes distribution summaries, missingness, delay by mode/region/time, a mode-by-period heatmap and the weather relationship. Extreme values are clipped only for plot readability, not silently deleted from the source.

Tests include:

- one-way ANOVA for mean differences by region and mode, with eta-squared;
- chi-squared tests for association between group and the five-minute-delay indicator, with Cramér's V;
- Spearman correlations between delay and weather variables.

Each inferential result contains a p-value. Multiple tests are exploratory; results should be discussed with effect sizes and not only statistical significance.

## Regression and evaluation

The explanatory model uses OLS on `log1p(delay_minutes)` with robust HC3 standard errors. It contains weather, weekend, region, mode and day-period terms. A region-by-mode interaction is included only when the observed design matrix has full rank; the generated model specification records any fallback.

The predictive model is a random-forest regressor with one-hot encoded categorical variables. A chronological train/test split is used when at least three service dates are present; otherwise a seeded development split is used and clearly labelled as preliminary.

Metrics:

- RMSE in minutes;
- MAE in minutes;
- R²;
- comparison with a mean-delay baseline;
- subgroup metrics by region and mode.

Permutation importance supports interpretation but is not a causal effect measure.

## k-means bonus analysis

Stations are aggregated to profile-level measures: mean, median and 90th-percentile delay, five-minute-delay rate and average weather. Features are standardized. Candidate k values from 2 to 6 are compared using silhouette score; the selected solution is visualized after PCA projection.

## Reproducibility

- Raw and generated data are excluded from Git by default.
- Every collector writes raw responses and does not overwrite older live snapshots.
- Random operations use seed 42.
- The Python environment is declared in `pyproject.toml`.
- Critical transformations have automated tests.
- SQL queries are stored as standalone files and executed from Python.
