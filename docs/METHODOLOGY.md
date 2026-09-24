# Methodology

## Research objective

The project estimates which observable factors are associated with reported public-transport delay and tests whether the associations differ across Swiss regions, transport modes and time periods.

The word **associated** is deliberate. The data are observational. The analysis does not identify causal effects.

## Research hypotheses

1. Reported delays differ across transport modes.
2. Reported delays differ across the seven Swiss large regions represented in the station panel.
3. Peak periods have a different delay distribution from off-peak periods.
4. Weather variables may be associated with reported delays; their direction is tested rather than assumed.
5. Region-by-mode differences may remain after adjusting for observed weather and time variables, if the panel supports the interaction.

## Unit of analysis

One row represents one reported vehicle call at a selected station and scheduled time. Repeated collector snapshots are deduplicated with a stable key that includes journey, scheduled time, event type, destination, operator and line. The latest available snapshot is retained. `snapshot_count` and `snapshot_lead_minutes` expose forecast repetition and timing; live API values are not claimed to be verified door-event measurements.

## Outcome variables

- `delay_minutes_signed`: reported minus scheduled time where a matching prognosis exists, or the API delay field; negative values indicate early running. Rows without a reportable delay are excluded and counted.
- `delay_minutes`: signed delay clipped at zero for the main regression.
- `is_delayed_5`: 1 when delay is at least five minutes, otherwise 0.

The five-minute threshold is a transparent project definition, not an official universal Swiss punctuality threshold.

## Sources and collection

### Live stationboard API

The recommended primary source is the JSON API at `transport.opendata.ch`. The group plans repeated stationboard snapshots every 15–30 minutes over 28 service days; this duration is a study-design target, not a lecturer rule. The API returns scheduled stops, prognoses, delay, transport category, operator and station coordinates. The collector explicitly requests departures. Stable keys collapse repeated snapshots to the latest observed report for each vehicle call. The sample captures selected stations and reported departures, not every Swiss movement.

Source and documentation: https://transport.opendata.ch/docs.html

### Actual data v2

The official Actual data v2 page supplies daily CSV files. A Python scraper discovers the resource links and a streaming collector can retain the selected station panel. This source supports a selected historical validation or an alternative design approved by the lecturer. A current daily file is about 670 MB, which makes a full 28-day download unnecessarily heavy for the primary design.

Source: https://data.opentransportdata.swiss/en/dataset/ist-daten-v2

### Weather

Open-Meteo provides hourly temperature, precipitation, snowfall, wind speed and wind gusts for each station coordinate. Historical dates use the archive endpoint and recent dates use the forecast endpoint. Both are requested in UTC. Source and retrieval time are saved for each row. Mixing forecast and archive products can alter comparability and must be described with the final data.

Source: https://open-meteo.com/en/docs/historical-weather-api

## Station panel and regional comparison

The panel deliberately includes rail hubs and urban stops in all seven Swiss large regions. Station identifiers and coordinates are resolved through the locations API. The configured canton-to-region assignment follows the official Swiss large-region concept, which is consistent with NUTS 2.

The panel is a stratified analytical sample. It is not a census of every stop and should not be used to rank whole regions without discussing coverage.

## Preparation

1. Normalize seven- and nine-digit BPUIC identifiers.
2. For live records compare the same scheduled and prognosis event (departure by design). For optional Actual data v2, use arrival if both times exist, otherwise departure.
3. Parse local Actual data timestamps in Europe/Zurich, and use the API offset for live data. Calculate and join on UTC timestamps; derive local service date and time periods afterward.
4. Calculate signed delay and a non-negative modeling target.
5. Keep the last timestamped report per observation key; record how many snapshots were collapsed.
6. Exclude missing/nonfinite targets, unmatched station-panel rows and signed delays outside the documented ±180-minute plausibility range. Record sequential row-loss reasons.
7. Add hour, weekday, weekend, peak period and broader day-period variables.
8. Join station metadata many-to-one on `station_id`.
9. Join weather many-to-one on normalized `station_id` plus scheduled UTC hour. Preserve unmatched transport rows; count both key matches and complete weather rows.

The generated audit tables record every row count and the weather match rate.

## EDA and statistical testing

EDA includes distribution summaries, missingness, delay by mode/region/time, a mode-by-period heatmap, daily coverage and the weather relationship. Regional results report both call-weighted and equal-station-weight means, because station sampling can distort a regional comparison. Extreme values are clipped only for plot readability, not silently deleted from the source.

Tests include:

- one-way ANOVA for mean differences by region, mode and time period, with eta-squared;
- chi-squared tests for association between group and the five-minute-delay indicator, with Cramér's V;
- Spearman correlations between station-hour mean delay and weather variables.

When computable, results include raw and Holm-adjusted p-values, sample size, effect size and an assumption/status note. Chi-squared tests report sparse expected cells. Tests are exploratory: repeated journeys, shared days, skewed delays and small cells limit classical p-value interpretation. A missing p-value means the statistic could not be computed.

## Regression and evaluation

The explanatory model uses OLS on `log1p(delay_minutes)` using complete weather cases. It contains weather, weekend, region, mode and day-period terms where the design is identifiable. A region-by-mode interaction is included only when observed cells provide full rank and residual degrees of freedom. Standard errors cluster by station when possible; with fewer than 30 stations and one service day, inference remains especially fragile. On this log1p outcome, `exp(beta)` is a ratio for fitted geometric means of delay plus one, rather than a percentage difference in arithmetic mean delay.

The predictive model is a random-forest regressor for raw delay minutes with one-hot encoded categories and train-fitted median imputation. Whole service dates are held out chronologically when at least two exist; a one-day development run holds out later whole scheduled timestamps and must not be presented as final performance. The model uses concurrent weather, so its evaluation describes retrospective association rather than an operational real-time forecast. The same training-mean baseline is evaluated on each group.

Metrics:

- RMSE in minutes;
- MAE in minutes;
- R²;
- comparison with a mean-delay baseline;
- subgroup metrics by region, mode and day period with sample sizes.

Permutation importance supports interpretation but is not a causal effect measure.

## k-means bonus analysis

Stations are aggregated to profile-level measures: mean, median and 90th-percentile delay, five-minute-delay rate and average weather. Features are standardized. Supported candidate k values from 2 to 6 are compared using silhouette score; the selected solution is visualized after PCA projection. Constant or unavailable features are recorded in the clustering specification.

## Reproducibility

- Raw and generated data are excluded from Git by default.
- Every collector writes raw responses and does not overwrite older live snapshots.
- Random operations use seed 42.
- The Python environment is declared in `pyproject.toml`.
- Critical transformations have automated tests.
- SQL queries are stored as standalone files and executed from Python.
- `sptdelays pipeline` rebuilds analysis from saved inputs with stage statuses, versions and SHA-256 hashes in `run_manifest.json`; it performs no API collection.
- `sptdelays validate` distinguishes structural data errors from configurable project coverage targets and manual submission requirements.
