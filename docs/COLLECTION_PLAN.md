# Final data collection plan

## Decision before collection

Obtain lecturer approval for the research question, station panel and repeated stationboard design. Replace group placeholders in the concept deck. Every group member should understand why the data support associations rather than causal conclusions.

## Recommended window

- Duration: target at least 28 consecutive service days (project study design, not a lecturer minimum).
- Frequency: one snapshot every 20 minutes.
- Coverage: weekdays, weekends, morning peak, daytime, evening peak and late service.
- Primary source: Swiss transport stationboard API.
- Enrichment source: Open-Meteo hourly weather, collected after transport preparation.

One snapshot currently returns about 700–750 rows for the 24-station panel. The preparation step removes repeated forecasts for the same station call by retaining the last snapshot.

## Daily commands

```powershell
uv run sptdelays collect-live
uv run sptdelays status
```

For an attended 24-hour run at 20-minute intervals:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_collection_loop.ps1 -IntervalMinutes 20 -Iterations 72
```

For unattended collection, configure Windows Task Scheduler to run `.venv\Scripts\sptdelays.exe collect-live` from the repository directory every 20 minutes. Use an account and power settings that keep the computer online. Test the task twice before relying on it.

## Monitoring

Check `uv run sptdelays status` daily. Investigate station failures, gaps longer than one hour, unlogged raw or normalized snapshot files and unexpected row-count changes. After preparation, inspect `reports/tables/daily_region_coverage.csv`: it shows every region on every calendar date, including zero usable-call cells. The files below form the collection evidence:

- `data/raw/transport_live/stationboards_*.json`
- `data/interim/collection_log.csv`
- `data/interim/live_snapshots/stationboards_*.csv` (one immutable normalized file per new snapshot)
- `data/interim/live_observations.csv` (read-only legacy data from the development run)

Preparation reads both normalized locations and deduplicates repeated vehicle calls. Back up the project folder during the collection period. Never manually edit raw JSON responses or normalized snapshot files.

## Collection completion criteria

- Target 28 distinct service dates; explain if approval/timing requires another design.
- All seven regions represented.
- Weekday and weekend coverage.
- No unexplained multi-hour gaps.
- Failed station requests documented.
- Group members and exact collection dates recorded in the presentation.

## Final analysis sequence

```powershell
uv run sptdelays prepare --source live
uv run sptdelays collect-weather
uv run sptdelays pipeline --source live
uv run pytest -p no:cacheprovider
```

The offline pipeline checks data, joins, databases, EDA, model and map from saved inputs and writes `run_manifest.json`. Review `quality_checks.csv`, especially calendar-date gaps and region-day coverage, plus the source mix in the weather log. Do not reuse the one-day development results as final evidence.
