# Data dictionary

| Variable | Type | Meaning / unit | Source or derivation |
|---|---|---|---|
| `observation_id` | string | Stable unique key for one station call | SHA-256 based project key |
| `data_source` | category | Official actuals v2 or live API | Collector |
| `station_id` | string | Normalized seven-digit Swiss stop identifier where possible | Transport source |
| `station_name` | string | Public stop name | Transport API / actuals v2 |
| `region` | category | One of seven Swiss large regions | Configured station panel |
| `canton` | category | Canton abbreviation | Configured station panel |
| `latitude`, `longitude` | float | WGS84 degrees | Locations/stationboard API |
| `journey_id` | string | Journey identifier | Transport source |
| `operator` | category | Transport operator abbreviation/name | Transport source |
| `category_raw` | string | Original product/category | Transport source |
| `transport_mode` | category | train, bus, tram, metro, ship, cableway, other | Normalized category |
| `line` | string | Customer-facing or technical line | Transport source |
| `scheduled_time` | datetime | Planned arrival/departure | Transport source |
| `reported_time` | datetime | Actual or last available forecast time | Transport source |
| `delay_minutes_signed` | float | reported minus scheduled, minutes | Calculated |
| `delay_source` | category | API delay field, prognosis difference or missing | Transport API normalization |
| `snapshot_count` | integer | Raw snapshots observed for this station call before deduplication | Preparation |
| `snapshot_lead_minutes` | float | Scheduled event minus time the API result was fetched; may be negative | Preparation of live data |
| `delay_minutes` | float | `max(0, delay_minutes_signed)` | Calculated |
| `is_delayed_5` | integer | 1 if delay ≥ 5 minutes | Calculated |
| `service_date` | date | Local scheduled date | Calculated |
| `scheduled_hour` | integer | Local hour 0–23 | Calculated |
| `weekday` | category | English weekday name | Calculated |
| `is_weekend` | integer | Saturday/Sunday indicator | Calculated |
| `is_peak` | integer | 06–08 or 16–18 indicator | Project definition |
| `day_period` | category | night, morning peak, midday, evening peak, evening | Project definition |
| `observation_hour` | datetime | Scheduled hour with UTC offset; parsed to UTC for joins | Calculated join key |
| `weather_matched`, `weather_complete` | boolean | Station-hour key matched / all configured weather values present | Weather integration |
| `weather_source` | category | Archive reanalysis, recent forecast or legacy source | Weather collector |
| `weather_fetched_at` | datetime | Time weather was retrieved | Weather collector |
| `temperature_2m` | float | °C | Open-Meteo |
| `precipitation` | float | mm during preceding hour | Open-Meteo |
| `snowfall` | float | cm | Open-Meteo |
| `wind_speed_10m` | float | km/h | Open-Meteo |
| `wind_gusts_10m` | float | km/h | Open-Meteo |

