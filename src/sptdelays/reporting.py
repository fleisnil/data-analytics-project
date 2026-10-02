"""A compact, source-linked results brief generated at the end of the pipeline."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import matplotlib.pyplot as plt
import pandas as pd

from .settings import PATHS

plt.switch_backend("Agg")


def _cell(value) -> str:
    if pd.isna(value):
        return "not available"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(frame: pd.DataFrame) -> str:
    header = "| " + " | ".join(map(str, frame.columns)) + " |\n"
    separator = "| " + " | ".join(["---"] * len(frame.columns)) + " |\n"
    return header + separator + "\n".join(
        "| " + " | ".join(_cell(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )


def write_analysis_summary() -> None:
    """Use only this run's saved tables; never infer that coverage means submission-ready."""
    def read_json(name):
        return json.loads((PATHS.tables / name).read_text(encoding="utf-8"))

    quality = read_json("quality_audit.json")
    specification = read_json("model_specification.json")
    temporal = read_json("temporal_validation.json")
    metrics = pd.read_csv(PATHS.tables / "model_metrics.csv")
    comparisons = pd.read_csv(PATHS.tables / "paired_model_comparisons.csv")
    rolling = pd.read_csv(PATHS.tables / "temporal_validation.csv")
    coverage = quality["coverage"]
    references = "; ".join(
        f"{term} = {category}" for term, category in specification["ols_reference_categories"].items()
    ) or "none (no categorical terms)"
    lines = [
        "# Swiss public transport delays — analysis brief", "",
        f"Generated: {datetime.now(UTC).isoformat()}. Rebuild with **Analyse starten**.", "",
        "## Research question", "",
        "Which factors are associated with public transport delays in Switzerland, and how do these associations differ between regions, transport modes and time periods?", "",
        f"**Data status: {quality['status']}**. Structural errors: {quality['errors']}; coverage warnings: {quality['warnings']}.", "",
        "Coverage checks are not proof of representativeness, lecturer approval or submission completion. All results describe the sampled station calls, not all Swiss public transport.", "",
        "## Data and unresolved limitations", "",
        f"- {coverage.get('rows', 0):,} prepared calls at {coverage.get('stations', 0)} stations.",
        f"- {coverage.get('service_dates', 0)} service date(s): {coverage.get('first_date')} to {coverage.get('last_date')}.",
        f"- Regions: {', '.join(coverage.get('regions', []))}.",
        f"- Modes: {', '.join(coverage.get('modes', []))}.",
        f"- Observed time periods: {', '.join(coverage.get('day_periods', []))}.", "",
    ]
    for check in quality["checks"]:
        if not check["passed"]:
            lines.append(f"- **{check['check']}**: {check['detail']}")
    lines += ["", "## Held-out model comparison", "",
              f"Split: `{specification['split_strategy']}`. Training rows: {specification['train_rows']}; test rows: {specification['test_rows']}.", "",
              "Errors are in minutes; lower MAE/RMSE is better. Signed bias is prediction minus actual delay (negative means underprediction). R-squared is undefined for constant targets and can be negative.", "",
              _table(metrics[["group", "n", "rmse", "mae", "r2", "mean_error_pred_minus_actual"]]), "",
              "![Held-out errors](figures/08_model_comparison.png)", "",
              "This chart shows point estimates, not uncertainty intervals. Do not choose or tune a model repeatedly on this final holdout.", "",
              "## Does weather add predictive information?", "",
              f"Ablation status: `{specification['weather_ablation_status']}`.", "",
              specification["weather_ablation_note"], "",
              "The following differences are full forest minus reference; negative favors the full forest. An interval containing zero does not establish a clear error difference. Missing intervals mean insufficient dates or unavailable weather features, not zero uncertainty.", "",
              _table(comparisons[["reference_prediction", "metric", "difference_rf_minus_reference",
                                  "ci_low", "ci_high", "test_dates", "status"]]), "",
              specification["uncertainty_note"], "",
              "Date-bootstrap intervals are exploratory and conditional on fitted models. They preserve within-day dependence but do not account for dependence between days or uncertainty from model training.", "",
              "## Stability across later periods", "",
              f"Temporal validation status: `{temporal['status']}`.", "", temporal["policy"], "",
              temporal["caveat"], ""]
    if rolling.empty:
        lines += ["**No temporal stability claim is supported by this run.** Collect more distinct service dates; do not manufacture folds by randomly splitting station calls.", ""]
    else:
        lines += [_table(rolling[["fold", "group", "n", "rmse", "mae", "validation_first_date",
                                  "validation_last_date"]]), ""]
    lines += ["## How to interpret the association model", "",
              f"OLS specification: `{specification['formula']}`.", "",
              f"OLS rows: {specification['ols_rows']}; excluded for missing model weather: {specification['ols_rows_excluded_missing_weather']}; station clusters: {specification['ols_station_clusters']}.", "",
              f"Reference categories: {references}.", "",
              "Use [all OLS coefficients and intervals](tables/ols_associations.csv), not only terms with small p-values. Categorical terms depend on their reference category; interaction effects require combined terms. exp(beta) refers to fitted geometric mean of delay + 1, not a percent change in arithmetic mean delay.", "",
              specification["ols_inference_caveat"], "",
              "## Evidence for the presentation and discussion", "",
              "- [Subgroup errors and sample sizes](tables/subgroup_metrics.csv): inspect regional, mode and period differences; small groups can be unstable.",
              "- [Unseen holdout categories](tables/holdout_coverage.csv): identify extrapolation to unseen groups.",
              "- [Statistical tests, effect sizes and corrected p-values](tables/statistical_tests.csv): corrections do not fix invalid assumptions.",
              "- [Integration audit](tables/integration_audit.csv) and [preparation audit](tables/preparation_audit.csv): account for matches and row losses.",
              "- [Station map](station_delay_map.html) and [cluster profiles](tables/cluster_profiles.csv): exploratory geographic context, not causal rankings.",
              "- [Run manifest](tables/run_manifest.json): input, code and selected result hashes; check that the run status is completed.", "",
              "## Next decisions for the group", "",
              "1. Resolve coverage warnings and collect the agreed multi-day sample before presenting final findings.",
              "2. Explain weather product provenance, sampling exclusions, comparisons and uncertainty in your own words.",
              "3. Review all subgroup results and temporal folds, not just the most favorable score.",
              "4. Complete lecturer approval, AI reflection, PDF evidence appendix, video and Moodle submission. A successful pipeline does not complete these human requirements.", ""]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    labels = metrics["group"].str.replace("_", " ")
    for axis, metric in zip(axes, ["rmse", "mae"], strict=True):
        axis.barh(labels, metrics[metric], color="#126d92")
        axis.set_xlabel(f"{metric.upper()} (minutes; lower is better)")
        axis.grid(axis="x", alpha=0.2)
    axes[0].invert_yaxis()
    figure.suptitle(f"Held-out error comparison — {quality['status']}")
    figure.tight_layout()
    figure.savefig(PATHS.figures / "08_model_comparison.png", dpi=160, bbox_inches="tight")
    plt.close(figure)
    output = PATHS.root / "reports" / "analysis_summary.md"
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Results brief created: {output}")
