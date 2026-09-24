# AI usage log

AI use is desired by the module, but every entry must be truthful and understood by the group. Add an entry whenever AI materially changes code, analysis or slides.

| Date | Tool | Task | Prompt/interaction summary | Output used? | Verification performed | Advantage | Problem or failure | Human correction/decision |
|---|---|---|---|---|---|---|---|---|
| 2026-09-17 | OpenAI Codex | Initial repository architecture | Asked for a project implementation aligned with the 22-point rubric | Yes | Official sources checked; tests and a live end-to-end run completed | Rapid integration of rubric and course methods | Cannot guarantee data quality or grade | Group must collect final data, understand code and validate all results |
| 2026-09-17 | OpenAI Codex | Data-source design | Compared Actual data v2 with repeated stationboard API collection | Yes | Web scraper returned official links; an HTTP range request showed a daily file of about 670 MB | Avoided an unnecessarily heavy 28-day download | Initial design treated Actual data v2 as the preferred primary source | Switched to group-owned repeated API snapshots and kept Actual data for validation |
| 2026-09-17 | OpenAI Codex | Pipeline debugging | Ran collection, preparation, weather join, databases, EDA and models | Yes | 730 raw rows, 629 prepared rows, 100% weather match; tests and Ruff passed | Found problems before final collection | Fixed timezone, plotting backend, environment loading and model-rank issues | Corrections are documented in `TECHNICAL_VALIDATION.md` |
| 2026-09-24 | OpenAI Codex | Project optimization | Asked to improve the complete project against the stated rubric while keeping its structure | Yes | 39 Python tests passed; offline pipeline and four notebooks executed; SQLite/DuckDB joins reconciled; see `TECHNICAL_VALIDATION.md` | Found leakage in preprocessing, ambiguous weather-hour handling, sparse tests and unlogged development raw data | The current panel spans one service day and cannot support final inferences; DuckDB acceptance and PostgreSQL runtime remain unverified | Group reviews the changed methods, collects approved multi-day data and interprets final figures itself |
| 2026-09-24 | OpenAI Codex | Collection and evaluation scaling | Asked for further improvement without prioritizing PowerPoint | Yes | 44 tests, Ruff and an offline pipeline run passed; no API data collected | Immutable normalized snapshot files avoid rewriting the full dataset; a holdout coverage table exposes unseen categories | One historical raw snapshot has no separate log entry; one-day coverage and weak weather provenance remain | Used the legacy CSV as the new counter baseline, retained all old data and documented remaining study limitations |
|  |  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |  |

## Required reflection for slides and video

Address all four questions with concrete examples:

1. Which AI tools were used and for which tasks?
2. What saved time or improved quality?
3. Where did AI produce an error, unsupported assumption or unsuitable solution?
4. How did the group test, correct and take responsibility for the final result?

Good evidence includes failed API assumptions, incorrect station IDs found during resolution, unit tests that caught a problem, and a model interpretation revised after checking the source documentation.
