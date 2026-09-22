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
│   └── collect_weather.py
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
