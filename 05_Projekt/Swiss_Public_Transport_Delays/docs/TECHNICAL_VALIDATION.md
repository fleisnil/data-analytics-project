# Technical validation record

Date: 17 September 2026  
Purpose: validate the implementation with a development snapshot. These numbers are not final project findings.

## Successful checks

- Resolved 24 configured stations through the locations API.
- The API corrected nine configured station identifiers; the resolved panel is stored in interim data.
- Collected 730 live stationboard rows in the first development snapshot.
- Prepared 629 plausible, panel-matched vehicle-call observations.
- Joined hourly Open-Meteo weather to 629 of 629 observations without changing the row count.
- Created the SQLite database and executed three SQL query groups from Python.
- Created a persistent DuckDB database and executed a SQL join plus regional/mode aggregations from Python.
- Generated EDA tables and figures plus ANOVA, chi-squared and Spearman outputs.
- Generated regression metrics, baseline comparison, subgroup metrics and OLS association output.
- Completed k-means clustering and the interactive geographic map.
- Discovered official Actual data v2 resource links through the dataset-page scraper.
- Verified that a current Actual data v2 daily file is approximately 670 MB before deciding against a 28-day full-file primary design.
- Passed five automated tests and all Ruff checks.

## Problems found and corrected

- Weather timestamps originally used a fixed `+0200` suffix. The collector now applies the Europe/Zurich timezone, including daylight-saving changes.
- Matplotlib initially requested a desktop Tk backend. EDA and clustering now use a headless backend.
- The first PostgreSQL setup instructions did not load `.env`. The loader now reads it explicitly.
- Sparse development data produced a rank-deficient region-mode interaction. The model now checks matrix rank and records a transparent fallback.
- Parallel model execution emitted excessive runtime warnings in the current Python environment. The reproducible model now uses one worker.

## Remaining validation

PostgreSQL requires a running Docker/PostgreSQL service and should be demonstrated by the group if the lecturer does not accept DuckDB as a similar database. The final multi-day collection must be rerun through the complete pipeline before any substantive result appears in the presentation.
