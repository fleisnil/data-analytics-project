# Data Dictionary

This file documents the main variables currently produced by the collection scripts. It will be extended when the integrated analysis dataset is built.

## OJP transport snapshot

| Column | Meaning |
| --- | --- |
| `batch_id` | Identifier of one collection run |
| `collection_timestamp` | UTC timestamp when the OJP request was made |
| `city` | Project region |
| `station_type` | `rail` or `local` observation point |
| `station_id` | Configured OJP/SLOID station identifier |
| `station_name` | Configured station name |
| `stop_point_ref` | Stop-point reference returned by OJP |
| `operating_day` | OJP operating day |
| `journey_ref` | OJP journey identifier |
| `transport_mode` | OJP public-transport mode |
| `product_category` | Product/category returned by OJP |
| `public_code` | Public service code |
| `line` | Published line/service name |
| `train_number` | Train/service number when available |
| `origin` | Service origin |
| `destination` | Service destination |
| `planned_platform` | Scheduled platform/quay |
| `estimated_platform` | Estimated platform/quay |
| `scheduled_departure` | Timetabled departure timestamp |
| `estimated_departure` | Real-time estimated departure timestamp |
| `cancelled` | Cancellation field returned by OJP when available |
| `has_realtime` | Whether `estimated_departure` is available |
| `predicted_delay_minutes` | `estimated_departure - scheduled_departure` in minutes |
| `date` | Local scheduled-departure date |
| `hour` | Local scheduled-departure hour |
| `weekday` | Local weekday name |
| `weekend` | Weekend indicator |
| `minutes_until_departure` | Scheduled departure minus collection time |

## MeteoSwiss weather snapshot

| Column | Meaning |
| --- | --- |
| `collection_timestamp` | UTC timestamp when the weather files were collected |
| `city` | Project region used for joining |
| `weather_station_abbr` | MeteoSwiss three-letter station code |
| `weather_station_name` | MeteoSwiss station name |
| `reference_timestamp` | MeteoSwiss measurement timestamp in UTC |
| `temperature_c` | Air temperature 2 m above ground |
| `precipitation_mm_10min` | Precipitation total for the 10-minute interval |
| `relative_humidity_pct` | Relative humidity 2 m above ground |
| `wind_speed_kmh_10min` | 10-minute mean wind speed |
| `wind_gust_kmh` | One-second gust maximum |
| `station_pressure_hpa` | Atmospheric pressure at barometric altitude (QFE) |
| `weather_age_minutes` | Collection timestamp minus measurement timestamp |
| `source_url` | MeteoSwiss source file used for the reading |
