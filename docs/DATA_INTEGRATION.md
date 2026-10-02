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

## Safe weather refreshes

Collection checks that requested columns exist and timestamps are unique, exact
UTC hours. Invalid/non-numeric/nonfinite weather values become missing values,
not zero. Failed station-window responses stay visible in the collection log;
saved raw JSON is linked even when its contents fail validation.

When a station-hour key already exists, compare the number of finite values
across the configured weather variables. Keep the more complete **whole row**;
on a tie, use the incoming fetch. Do not combine individual values from forecast
and reanalysis into a row with misleading provenance. Missing old variables
count as missing. Consequently an older forecast can be retained over an
incomplete archive row: this is explicitly audited, and is not a claim that the
forecast is more accurate. Entirely new incomplete rows remain visible to the
normal missingness and coverage checks.

`reports/tables/weather_update_audit.csv` records each incoming key, old/new
usable-variable counts, the selection decision and incoming/selected provenance.
It describes the latest successful refresh; archive it with the corresponding
data if needed for comparisons. Raw responses and the collection log retain the
fetch history. Each CSV is replaced atomically; the data, log and audit are not
a single database transaction. An interrupted collection should be inspected
before rerunning. A wholly failed fetch leaves the previous weather CSV intact.

## Required evidence after each final run

Use these generated files in the notebook and points appendix:

- `reports/tables/preparation_audit.csv`
- `reports/tables/integration_audit.csv`
- `reports/tables/missingness.csv`
- `reports/tables/weather_unmatched_keys.csv`, `quality_checks.csv` and `quality_audit.json`
- `reports/tables/sqlite_storage_audit.json` and `duckdb_storage_audit.json`
- screenshot of the relevant merge code and audit table

The report must state the raw row count, duplicate rows removed, unmatched station rows, implausible/missing delay rows removed, weather matches and final row count.

