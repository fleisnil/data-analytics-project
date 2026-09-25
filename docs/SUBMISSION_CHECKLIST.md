# Submission checklist

## Before concept presentation

- [ ] Lecturer approved the topic on-site in Winterthur.
- [ ] Research question and four to five hypotheses fit on one slide.
- [ ] Explain the unit of analysis and the planned collection period.
- [ ] Show the official transport source, weather source and integration keys.
- [ ] Explain why the question goes beyond a standard prediction task.
- [ ] Every group member can explain the methods.

## Before final analysis

- [ ] Meet or justify the planned 28 service dates, including weekdays and weekends (project target, not lecturer minimum).
- [ ] Resolve and manually inspect every station ID.
- [ ] Save collection dates and source URLs.
- [ ] Inspect missingness by region, mode and operator.
- [ ] Review duplicate removal and all row losses.
- [ ] Confirm weather units, archive-versus-forecast mix, join rate and complete-value rate.
- [ ] Run `sptdelays status`; resolve unlogged raw snapshots and collection gaps.
- [ ] Run `sptdelays validate`; review every error and coverage warning.
- [ ] Use a chronological holdout and compare with both overall and group-mean training baselines; report sparse/unseen group fallbacks.
- [ ] Report exact metrics and p-values with effect sizes.
- [ ] Re-run tests from a clean environment.
- [ ] Execute all four notebooks using `python scripts/check_notebooks.py --execute`.
- [ ] Inspect `run_manifest.json`, SQL storage audits and actual presentation numbers.
- [ ] Review every interpretation for non-causal language.

## Moodle submission

- [ ] `video_recording_group_XX.mp4` or correctly numbered parts.
- [ ] `materials_group_XX.zip` containing data allowed for redistribution and all notebooks.
- [ ] Inspect the package file list with `scripts/build_submission.ps1 -ValidateOnly` before building it; verify there are no secrets or unexpectedly omitted data.
- [ ] `presentation_group_XX.pdf` with required structure.
- [ ] PDF appendix maps claimed points to screenshots/code/results.
- [ ] AI reflection appears in slides and video.
- [ ] Public GitHub URL appears in the presentation after group review.
- [ ] One student uploads for the group using the correct group number.
- [ ] Confirm the actual deadline with the lecturer because Moodle contains conflicting fields.

