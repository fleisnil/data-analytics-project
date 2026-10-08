# Methodology Notes

## 1. Public-transport observation design

The project observes eight Swiss transport regions. Each region contains:

- one rail stop
- one nearby local-public-transport stop where available

This deliberately creates comparable regional observation points while still covering multiple transport modes.

Current modes observed in the pilot include rail, bus, tram and metro.

## 2. OJP snapshot semantics

Every run is a snapshot of upcoming departures.

A single physical journey may appear in several snapshots. Repeated snapshots are useful for studying how the real-time estimate changes, but they must not automatically be treated as independent journeys in the final modelling dataset.

Candidate journey identity:

- `journey_ref`
- `operating_day`
- `station_id`

`collection_timestamp` distinguishes repeated observations of the same journey.

## 3. Delay variable

The current derived variable is:

```text
predicted_delay_minutes = estimated_departure - scheduled_departure
```

This is based on OJP `EstimatedTime`.

Consequences:

- it is a real-time estimate, not automatically the final realised delay
- missing `EstimatedTime` stays missing
- negative values are retained because an estimate can indicate an earlier departure
- no automatic clipping to zero is applied

## 4. Observation-window strategy

Before modelling, the project will select one consistent observation per journey/stop.

A candidate rule is the final available observation within a fixed pre-departure window (for example 5–15 minutes before scheduled departure). The final window will be selected after inspecting coverage.

The analysis must report:

- number of raw snapshot rows
- number of unique journeys
- number of rows retained by the observation-window rule
- rows removed or unavailable

## 5. Weather source and regional mapping

Weather comes from MeteoSwiss SwissMetNet 10-minute observations.

Current mapping:

| Region | MeteoSwiss station |
| --- | --- |
| Zürich | SMA — Zürich / Fluntern |
| Bern | BER — Bern / Zollikofen |
| Basel | BAS — Basel / Binningen |
| Luzern | LUZ — Luzern |
| St. Gallen | STG — St. Gallen |
| Lausanne | PUY — Pully |
| Genève | GVE — Genève / Cointrin |
| Lugano | LUG — Lugano |

The mapping is regional rather than stop-platform-specific. This limitation must be stated in the final report.

MeteoSwiss reference timestamps are UTC.

## 6. Planned OJP–weather integration

The final join will use:

1. region/city mapping
2. nearest available MeteoSwiss timestamp to the selected OJP observation timestamp

The join will retain a time-difference variable so join quality can be evaluated.

The project will explicitly document:

- OJP rows before the join
- matched rows
- unmatched rows
- maximum/median weather time difference
- any rows excluded because weather measurements are too far from the transport observation

## 7. Planned target for classification

A possible target is:

```text
is_predicted_delayed = predicted_delay_minutes >= 5
```

The threshold is not final yet and must be justified in the analysis.

The classification task will be used to study associations with operational, temporal and weather-related predictors rather than merely to maximise prediction accuracy.

## 8. Planned comparisons

The analysis is intended to compare:

- regions/cities
- transport modes
- rail vs local public transport
- weekday vs weekend
- hour/time period
- weather conditions
- possibly different stages of the collection period

## 9. Database requirement

SQLite is implemented in `src/database.py`.

The local database is generated at:

```text
data/database/transport_weather.sqlite
```

It contains:

- `transport_observations`
- `weather_observations`
- `stations`

The SQL view `transport_weather_joined` performs a real SQL join between the two independently collected sources. It matches each selected OJP observation to the newest MeteoSwiss observation in the same city that is not from the future and is at most 30 minutes old.

SQL statements are stored in `sql/schema.sql` and `sql/analysis_queries.sql` and are executed from Python. The analysis queries include aggregations with `GROUP BY` as well as the cross-source SQL join.

The SQLite database is reproducible and therefore ignored by Git. PostgreSQL may be added later as a bonus extension.


## 10. Automated collection and analysis sync

GitHub Actions stores compact OJP and MeteoSwiss CSV snapshots on the separate `data-collection` branch. The development and analysis code remains on `main`.

`src/sync_collection_data.py` fetches `origin/data-collection` and copies the archived snapshots into the ignored local `data/interim/` directories without checking out the data branch.

After synchronization, `src/build_dataset.py` can use both local MeteoSwiss raw files and the compact archived weather snapshots. This keeps the automated archive small while allowing the final multi-week analysis to use all collected runs.


## 11. Exploratory data analysis

Exploratory analysis is implemented in `src/eda.py`.

The EDA always starts from the integrated analysis dataset after the one-observation-per-journey/stop selection. This avoids allowing frequently repeated snapshots of the same journey to dominate descriptive results.

The script produces both non-graphical and graphical EDA. Non-graphical outputs include missingness, delay summaries, city/mode summaries, hourly summaries and weather summaries. Graphical outputs cover distributions, regional and modal comparisons, weekday/hour patterns, weather relationships, temporal coverage and sample balance.

Delay rates are shown as percentages within groups rather than raw delayed counts wherever possible. This is important because the number of selected observations can differ across regions and transport modes.

The collection is still growing. Current EDA output must therefore be described as provisional and descriptive rather than as evidence of stable differences or causal weather effects.


## 12. Statistical tests

Inferential statistics are implemented in `src/statistics_analysis.py`.

The delay distribution is strongly non-normal and contains many observations close to zero. Therefore the main group comparison uses the non-parametric Kruskal-Wallis test rather than relying only on a mean-based ANOVA. The output also reports epsilon-squared as an effect-size measure.

A Chi-square test evaluates the association between transport mode and the provisional five-minute delayed/not-delayed indicator. The script reports Cramer's V and explicitly checks whether all expected cell counts are at least five. A city-level Chi-square result is also produced, but it must not be interpreted when the expected-count assumption is violated.

Weather p-values require special care because many departures can share exactly the same MeteoSwiss observation. The script therefore first aggregates the transport observations by city and weather reference timestamp. Spearman correlations are calculated both overall and after within-city centering, which reduces simple confounding from persistent differences between regions.

A Mann-Whitney U comparison is included for wet versus dry weather groups. Its result must be interpreted together with the number of wet groups because precipitation can still be sparse.

Finally, the script reports the observed positive-class share for delay thresholds from one to five minutes. This is used to justify the eventual modelling target instead of selecting the five-minute threshold without checking class balance.
