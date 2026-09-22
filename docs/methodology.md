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

A SQLite database will be created from Python for the minimum project requirement.

Planned tables include:

- transport observations
- weather observations
- station/region metadata

SQL queries will be executed from Python and include aggregations and joins. PostgreSQL may be added later as a bonus extension.
