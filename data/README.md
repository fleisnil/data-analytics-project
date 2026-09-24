# Data folders

- `raw/`: immutable API responses and selected official source files.
- `interim/`: immutable normalized files in `live_snapshots/`, read-only legacy `live_observations.csv`, station resolution, weather and collection log.
- `processed/`: the integrated modeling dataset.

Downloaded and generated data are ignored by Git because they can be large. Keep them for the Moodle materials ZIP and document source licences before public redistribution. Never overwrite or manually correct raw responses. Put corrections in the preparation code and preserve the audit trail.

