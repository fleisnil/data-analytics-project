# Data integration and audit plan

## Keys

| Join | Left key | Right key | Expected relationship |
|---|---|---|---|
| Actuals → station panel | normalized `BPUIC` | resolved `station_id` | many-to-one |
| Live stationboard → station panel | API station ID | resolved `station_id` | many-to-one |
| Transport → weather | normalized `station_id` + scheduled UTC hour | normalized `station_id` + weather UTC hour | many-to-one |

## Inconsistencies handled

- BPUIC may contain seven digits, nine digits for stop edges, or an SLOID. Nine-digit Swiss values are normalized to the first seven digits for the station-level panel.
- German and API-specific transport categories are mapped to common modes.
- Arrival can be unavailable at origin stops and departure can be unavailable at terminal stops. The project uses arrival where both scheduled and reported values exist, otherwise departure.
- Actuals times are parsed in `Europe/Zurich` and converted to UTC for arithmetic. Live API times contain offsets. UTC hour keys distinguish the repeated hour during the autumn daylight-saving transition. Local service dates and peak periods remain in `Europe/Zurich`.
- Reported values can be actual, estimated or forecasts. Status is preserved and discussed.
- Missing weather is retained after a left join and counted; rows are not silently removed during integration. Matched station-hour keys and complete weather-variable rows are reported separately.

## Required evidence after each final run

Use these generated files in the notebook and points appendix:

- `reports/tables/preparation_audit.csv`
- `reports/tables/integration_audit.csv`
- `reports/tables/missingness.csv`
- `reports/tables/weather_unmatched_keys.csv`, `quality_checks.csv` and `quality_audit.json`
- `reports/tables/sqlite_storage_audit.json` and `duckdb_storage_audit.json`
- screenshot of the relevant merge code and audit table

The report must state the raw row count, duplicate rows removed, unmatched station rows, implausible/missing delay rows removed, weather matches and final row count.

