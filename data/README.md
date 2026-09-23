# Data directories

Generated collection files are intentionally excluded from normal Git tracking.

- `raw/ojp/`: raw OJP XML responses
- `raw/weather/`: raw MeteoSwiss CSV responses
- `interim/ojp_snapshots/`: combined OJP snapshots
- `interim/weather_snapshots/`: combined weather snapshots
- `processed/`: reproducible integrated analysis datasets
- `database/`: locally generated SQLite database

A small sample dataset may be committed deliberately for reproducibility, but the continuous collection output should not be added with `git add .`.
