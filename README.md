# Swiss Public Transport Delays

Data Analytics project about public-transport delay patterns in Switzerland.

## Research question

**Which operational, temporal and weather-related factors are associated with public transport delays in Switzerland, and how do these associations differ across regions and transport modes?**

The project uses observational data. We therefore describe **associations**, not causal effects.

## Current scope

Eight Swiss transport hubs are observed:

- Zürich
- Bern
- Basel
- Luzern
- St. Gallen
- Lausanne
- Genève
- Lugano

For every region the OJP collector observes one rail stop and one nearby local-public-transport stop. This gives 16 OJP observation points covering rail, bus, tram and metro services.

Weather is collected from nearby MeteoSwiss SwissMetNet stations for the same eight regions.

## Data sources

### 1. Open Journey Planner (OJP 2.0)

Source: Open Transport Data Switzerland.

`src/collect_all_stations.py` queries the selected public-transport stops and stores:

- raw XML responses
- one combined CSV snapshot per run
- scheduled and estimated departure timestamps
- transport mode, line, origin/destination and platform information
- derived temporal variables

Important semantic note: OJP `EstimatedTime` is a real-time estimate. The derived column `predicted_delay_minutes` must therefore not be presented as a final realised delay unless a later methodology establishes that interpretation.

Missing `EstimatedTime` remains missing and is **not** converted to zero delay.

### 2. MeteoSwiss SwissMetNet

Source: MeteoSwiss Open Data.

`src/collect_weather.py` downloads the current 10-minute measurements from the automatic SwissMetNet stations and keeps the latest available reading for each project region.

Weather variables currently include:

- air temperature
- 10-minute precipitation
- relative humidity
- 10-minute mean wind speed
- wind gust
- station pressure

MeteoSwiss reference timestamps are UTC.

## Project structure

```text
.
├── 01_pilot_ojp_final_clean.ipynb
├── README.md
├── requirements.txt
├── src/
│   ├── collect_all_stations.py
│   ├── collect_weather.py
│   ├── build_dataset.py
│   └── database.py
├── data/
│   ├── raw/
│   │   ├── ojp/
│   │   └── weather/
│   ├── interim/
│   │   ├── ojp_snapshots/
│   │   └── weather_snapshots/
│   └── processed/
├── notebooks/
├── sql/
│   ├── schema.sql
│   └── analysis_queries.sql
├── results/
│   ├── figures/
│   ├── tables/
│   └── model/
└── docs/
    ├── ai_usage.md
    ├── data_dictionary.md
    └── methodology.md
```

Generated raw/interim data are ignored by Git to prevent the repository from growing continuously. Small samples can be committed deliberately when needed for reproducibility.

## Running the collectors

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the OJP collector:

```bash
python src/collect_all_stations.py
```

For unattended OJP collection, set the API token as environment variable:

```bash
export OJP_API_TOKEN="..."
python src/collect_all_stations.py
```

Run the MeteoSwiss collector:

```bash
python src/collect_weather.py
```

MeteoSwiss Open Data does not require the OJP token.

Sync the persisted collection data from the `data-collection` branch:

```bash
python src/sync_collection_data.py
```

This fetches the latest `data-collection` branch and copies all archived OJP/weather snapshots into the ignored local `data/interim/` folders without switching away from `main`.

Then build the integrated OJP + weather dataset:

```bash
python src/build_dataset.py
```

Build and validate the SQLite database:

```bash
python src/database.py
```

Generate the reproducible EDA tables and visualisations:

```bash
python src/eda.py
```

The EDA script creates descriptive CSV tables in `results/tables/` and PNG figures in `results/figures/`. These outputs are regenerated from the current analysis dataset and remain ignored by Git.

This creates `data/database/transport_weather.sqlite` locally and executes the documented SQL queries from `sql/analysis_queries.sql`. The SQLite file and generated result CSVs are reproducible outputs and are not committed to Git.

Run the SQLite unit test:

```bash
python -m unittest tests/test_database.py -v
```

### SQLite structure

The database contains:

- `transport_observations` — one selected 5–15 minute pre-departure observation per journey/stop
- `weather_observations` — deduplicated MeteoSwiss 10-minute measurements
- `stations` — OJP and MeteoSwiss station metadata
- `transport_weather_joined` — SQL view joining OJP and MeteoSwiss by city and the latest non-future weather timestamp within 30 minutes

The SQL queries include row counts, city/mode delay summaries, weather-join quality, delay summaries with weather, and hourly delay summaries.

## Automated collection

GitHub Actions runs `.github/workflows/collect_data.yml` every 30 minutes at minute 7 and 37. It collects OJP and MeteoSwiss data and commits only the compact CSV snapshots to the separate `data-collection` branch.

For analysis on `main`, use:

```bash
python src/sync_collection_data.py
python src/build_dataset.py
python src/database.py
python src/eda.py
```

The sync script does not switch branches and does not commit data to `main`.

## Planned analytics pipeline

1. Collect OJP and weather snapshots over multiple weeks.
2. Build one clean analysis dataset.
3. Select a consistent pre-departure observation per journey/stop to avoid repeated snapshots dominating the analysis.
4. Join public-transport and weather data by region and nearest timestamp, while documenting unmatched records and time differences.
5. Store/query the data with SQLite from Python.
6. Perform non-graphical and graphical exploratory data analysis.
7. Compare delay patterns across regions, transport modes, weekdays and time periods.
8. Run statistical tests where appropriate.
9. Build and evaluate a classification model for a documented delay threshold.
10. Interpret model results in relation to the research question.

### Current EDA outputs

The EDA code currently generates:

- overall row/date/mode/delay summary
- missing-value table
- city × transport-mode summary
- hourly summary
- weather-variable summary
- predicted-delay histogram
- delay rate by transport mode
- average delay by city/region
- boxplots by transport mode
- weekday × region heatmap
- hourly delay pattern
- temperature vs delay
- precipitation vs delay
- collection coverage over time
- daily average delay
- sample-balance plot by city and mode

All current EDA results are descriptive and provisional while automated collection is still running.

## Planned visualisations

Core visualisations will include:

- delay distribution
- delay rate by transport mode
- city/region comparison
- boxplots by mode and region
- weekday × region heatmap
- hourly delay pattern
- weather vs delay plots
- collection-period time series
- model confusion matrix / ROC or precision-recall curve
- feature importance

A geographic map can be added as a bonus analysis.

## Reproducibility and AI use

Important data-processing decisions, limitations and join logic are documented in `docs/methodology.md`.

AI-assisted work, including failed approaches and validation steps, is documented in `docs/ai_usage.md`.
