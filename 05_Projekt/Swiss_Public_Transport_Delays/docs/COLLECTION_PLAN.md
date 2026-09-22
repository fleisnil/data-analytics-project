# Final data collection plan

## Decision before collection

Obtain lecturer approval for the research question, station panel and repeated stationboard design. Replace group placeholders in the concept deck. Every group member should understand why the data support associations rather than causal conclusions.

## Recommended window

- Duration: at least 28 consecutive service days.
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

For unattended collection, configure Windows Task Scheduler to run `uv run sptdelays collect-live` from the repository directory every 20 minutes. Use an account and power settings that keep the computer online. Test the task twice before relying on it.

## Monitoring

Check `uv run sptdelays status` daily. Investigate station failures, gaps longer than one hour and unexpected row-count changes. The files below form the collection evidence:

- `data/raw/transport_live/stationboards_*.json`
- `data/interim/collection_log.csv`
- `data/interim/live_observations.csv`

Back up the project folder during the collection period. Never manually edit raw JSON responses.

## Collection completion criteria

- At least 28 distinct service dates.
- All seven regions represented.
- Weekday and weekend coverage.
- No unexplained multi-hour gaps.
- Failed station requests documented.
- Group members and exact collection dates recorded in the presentation.

## Final analysis sequence

```powershell
uv run sptdelays prepare --source live
uv run sptdelays collect-weather
uv run sptdelays integrate
uv run sptdelays sqlite
uv run sptdelays duckdb
uv run sptdelays analyse
uv run sptdelays model
uv run sptdelays cluster
uv run sptdelays map
uv run pytest
```

Do not reuse the one-snapshot development results as final evidence.
