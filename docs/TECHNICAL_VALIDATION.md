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

## Optimization run: 24 September 2026

The earlier figures above record the first development run and are intentionally retained as history. With the optimized code and the **same saved one-day inputs**:

- 1,467 raw transport observations, 25 duplicate event-key rows and 283 rows without a reportable delay led to 1,159 prepared station calls. Station matching did not add or lose rows.
- Weather matched and had all five configured variables for 1,159/1,159 prepared rows. This checks join mechanics only; it does not establish weather-source quality or representativeness.
- SQLite and DuckDB both joined 1,159 unique observations with zero row gain/loss. Their storage audits are saved in `reports/tables/`.
- `sptdelays pipeline --source live` completed without API calls and wrote a hashed run manifest. The data audit reported zero structural errors and four coverage warnings: one service date, no weekend, only two observed time periods, and no explicit weather-product provenance in the older development CSV. The current collector records this source for future runs.
- An independent holdout by later scheduled timestamps within that single day produced 53 test rows. Its RMSE was 0.357 minutes for the random forest and 0.400 minutes for the training-mean baseline. These are development diagnostics and **must not** be presented as final study findings.
- The OLS model had 24 station clusters. Its region-mode interaction was unidentifiable in this sparse panel and was omitted with a recorded reason. Small-cluster and shared-day dependence make p-values fragile. Several chi-squared expected counts were below five; these tests are flagged in the result table.
- 39 focused Python tests passed in the first combined run. Ruff reported two style findings, which were corrected; a final verification is recorded by the current command output rather than assumed here.
- All four Jupyter notebooks executed successfully against saved inputs. `scripts/build_submission.ps1 -ValidateOnly` listed 147 currently packageable files without writing an archive.

There are two saved raw snapshot JSON files but only one entry in `collection_log.csv`; `sptdelays status` reports the unlogged file. This historical development-log gap must be disclosed, not silently invented or backfilled. Future collector runs write timestamped raw evidence and logs together.

## Follow-up optimization: 24 September 2026

- New live collections write one immutable normalized CSV per snapshot. The older `live_observations.csv` is preserved as a read-only input; preparation merges legacy and new files. The collector no longer reloads and rewrites the growing observation history on every call.
- The cumulative collector count starts from the legacy CSV when old log entries undercount it. A test covers this historical mismatch, and status also flags normalized snapshot files that lack log entries.
- `holdout_coverage.csv` now lists unseen test-period categories, their affected row counts and proportions, plus unseen station IDs as a diagnostic. The current one-day development holdout has zero unseen rows in these checked fields; this does not remove its temporal-coverage limitation.
- 44 automated tests and Ruff passed. An offline pipeline rebuild on the saved data completed with zero structural errors and the same four study-coverage warnings. No new transport or weather data were fetched, and the numbers remain development diagnostics.
