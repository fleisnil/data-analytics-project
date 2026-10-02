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

## Coverage and evaluation follow-up: 25 September 2026

- Quality checks now distinguish 28 distinct dates from a continuous calendar window and test whether each observed region has usable rows on at least 80% of observed service dates. These are configurable project targets, not lecturer requirements. The new `daily_region_coverage.csv` includes zero-observation region-days between the first and last date.
- A training-only region/mode/day-period mean baseline joins the existing overall training mean. Combinations with fewer than ten training rows fall back to the overall mean; the fallback count is recorded in `model_specification.json` and each affected holdout row is marked.
- On the unchanged one-day development holdout of 53 rows, RMSE was 0.357 minutes for the forest, 0.380 for the group baseline and 0.400 for the overall mean. Two group-baseline holdout rows used the documented fallback. These values are **not final study results**.
- The offline pipeline and all four Jupyter notebooks executed successfully with the saved inputs. The audit reported zero structural errors and the same four pre-existing study-coverage warnings. 47 automated tests and Ruff passed. No new API data were fetched.

## Input readiness and collection resilience: 2 October 2026

- Added the read-only `doctor` command and VS Code **Startbereitschaft prüfen** action. Missing, empty or unreadable inputs are identified together, with recovery steps. Tests cover live/actuals source isolation, a fresh checkout, an empty resolved panel, CLI exit codes and preservation of an earlier run manifest when preflight fails. This checks file availability, not schema correctness or study readiness.
- Preparation now explicitly disables automatic station resolution. The earlier offline runs had a saved resolved panel, but the missing-panel fallback could previously call the API. A regression test now prevents that behavior.
- Weather responses must supply requested columns and unique, exact UTC hours. Refreshes preserve a more complete whole prior row, and record their selection in `weather_update_audit.csv`. Equal completeness prefers the incoming fetch. Provenance is kept with its row, not attached to a mixture of weather products.
- Weather CSV writes use a temporary sibling followed by atomic replacement. Tests simulate a failed write and a wholly failed collection, verify old data survive, and cover a partial update, legacy provenance and duplicate normalized keys. No live weather API was contacted in these tests.
- Final check: **68 tests passed**, with no warnings, and **Ruff passed**. The read-only doctor passed on saved inputs. The complete saved-data pipeline rebuilt SQLite, DuckDB, EDA, models, clustering and the map: 1,467 raw transport rows, 1,159 prepared rows, 1,159 weather matches, zero join row gain/loss and zero structural errors.
- The same four limitations remain: one service date, no weekend observations, only midday/evening-peak observations and missing product provenance in the legacy weather file. No new API data were collected. Notebook execution and PostgreSQL were not repeated in this follow-up.

## Stronger research evaluation: 2 October 2026

- All four prediction comparators (full forest, no-weather forest, overall-mean baseline, group-mean baseline) use identical held-out rows. Tests verify that changing test targets does not change fitted predictions, that all weather fields are excluded from the ablation, and that missing training weather cannot be recovered from future test values.
- Expanding date validation operates exclusively on the development partition; tests assert that whole dates remain together, shuffled/unequal call counts do not break chronology and the final holdout never enters any fold. Only one fold is materialized at a time to reduce memory use for larger collections.
- The paired whole-date bootstrap was checked against explicit whole-day resampling, including unequal numbers of calls, identical predictions, known error differences, deterministic seeds and rejection of nonfinite predictions. A single day never receives an uncertainty interval.
- An isolated 25-date synthetic integration test exercised all three chronological folds and five held-out dates with bootstrap intervals. Its files were confined to the temporary test directory. These synthetic values are not study data or evidence for transport/weather findings.
- Final verification: **80 tests passed without warnings**, Ruff passed, all four notebooks executed, and the full saved-data pipeline completed with 1,159 prepared calls, zero structural errors and the same four data-coverage warnings. Notebook execution emitted Windows event-loop fallback and kernel TCP-transport warnings; no notebook failed and no transport configuration was changed. PostgreSQL was not exercised in this follow-up.
- On the unchanged 53-row, one-day development holdout, full-forest RMSE was 0.357 minutes versus 0.388 without weather, 0.380 for the group mean and 0.400 for the overall mean. These are point diagnostics only. All date-bootstrap intervals were correctly withheld and temporal validation was marked `insufficient_development_data`.
- The generated English brief `reports/analysis_summary.md` and `08_model_comparison.png` expose these limitations alongside model metrics and evidence links. OLS reference levels come from the fitted design, using compatible metadata access for the installed statsmodels version. The initial incompatible access was caught and corrected before committing.
- Notebook 01 now respects offline mode even without saved station resolutions and reads both legacy observations and immutable snapshot parts. Notebook 04 includes the new comparison and temporal-validation tables. The run manifest now fingerprints the brief, comparison plot and selected evaluation artifacts in addition to the processed dataset.
