"""Render the main analysis brief from existing results, without recalculating them."""

from __future__ import annotations

import csv
import math
from pathlib import Path

MODELS = {
    "median_baseline": "Global median",
    "group_median": "City / mode / time median",
    "linear_regression": "Linear regression",
    "random_forest": "Random forest",
    "random_forest_no_weather": "Random forest without weather",
    "gradient_boosting_mae": "Gradient boosting",
}


def rows(path: Path):
    if path.is_file():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)


def number(value):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result if math.isfinite(result) else None


def fmt(value, spec=".4f"):
    result = number(value)
    return format(result, spec) if result is not None else "—"


def label(value):
    return MODELS.get(value, value or "Not recorded")


def cell(value):
    return str(value or "—").replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def table(headers, values):
    def line(fields):
        return "| " + " | ".join(cell(field) for field in fields) + " |"

    return [line(headers), line(["---"] * len(headers)), *(line(row) for row in values), ""]


def coverage(dataset: Path):
    fields = ("operating_day", "station_id", "city", "transport_mode")
    values = {field: set() for field in fields}
    for row in rows(dataset):
        for field in fields:
            if value := row.get(field):
                values[field].add(value)
    return {field: sorted(found) for field, found in values.items()}


def paired_section(comparisons):
    if not comparisons:
        return ["No comparison was available for this run.", ""]
    lines = table(("Model", "Reference", "Metric", "Difference (min)", "95% interval", "Test dates"), [
        (label(row.get("model")), label(row.get("reference")), (row.get("metric") or "—").upper(),
         fmt(row.get("difference")),
         f"{fmt(row.get('ci_low'))} to {fmt(row.get('ci_high'))}"
         if number(row.get("ci_low")) is not None and number(row.get("ci_high")) is not None
         else "Not available",
         fmt(row.get("test_dates"), ",.0f")) for row in comparisons
    ])
    return lines


def build_summary(root: Path, figures: list[Path], generated: str) -> str:
    tables = root / "results/tables"
    integration = {
        row.get("metric"): row.get("value") for row in rows(tables / "data_integration_report.csv")
    }
    sample = coverage(root / "data/processed/analysis_dataset.csv")
    benchmarks = list(rows(tables / "model_holdout_benchmarks.csv"))
    splits = {row.get("split"): row for row in rows(tables / "model_split_summary.csv")}
    selection = next(rows(tables / "model_selection_summary.csv"), {})
    selected = selection.get("best_model")
    selected_label = label(selected)
    paired = list(rows(tables / "model_paired_comparisons.csv"))
    weather = [row for row in paired if row.get("reference") == "random_forest_no_weather"]
    baselines = [row for row in paired if row not in weather]
    validation = list(rows(tables / "model_temporal_validation.csv"))
    findings = {
        row.get("topic"): row for row in rows(tables / "final_key_findings.csv")
    }
    day = sample["operating_day"]
    names = {figure.name for figure in figures}
    lines = [
        "# Swiss public transport delays — analysis brief", "",
        f"Generated: {generated}. Rebuild with **Analyse starten**.", "",
        "## Research question", "",
        "Which operational, temporal and weather-related factors are associated with public transport "
        "delays in Switzerland, and how do these associations differ by city, mode and time period?", "",
        "## Data and unresolved limitations", "",
        f"- **{fmt(integration.get('selected_unique_journey_stops'), ',.0f')} observations** selected "
        f"from {fmt(integration.get('ojp_raw_rows'), ',.0f')} raw OJP rows.",
    ]
    if day:
        lines.append(
            f"- **{len(day)} observed operating days** ({day[0]} to {day[-1]}), "
            f"**{len(sample['station_id'])} transport stops** across **{len(sample['city'])} cities**. "
            "The date range can contain gaps."
        )
    if sample["transport_mode"]:
        lines.append("- Modes in the analysed sample: " + ", ".join(sample["transport_mode"]) + ".")
    lines.extend([
        f"- **Weather match: {fmt(integration.get('weather_match_rate_pct'), '.2f')}%** "
        f"({fmt(integration.get('weather_matched_rows'), ',.0f')} matched; "
        f"{fmt(integration.get('weather_unmatched_rows'), ',.0f')} unmatched).", "",
        "OJP reports **estimated departure delays 5–15 minutes before departure**, not final realised "
        "delays. Weather is linked by city and observation time. The sampled hubs are not representative "
        "of the whole Swiss network; associations are not causal.", "",
        "## Held-out model comparison", "",
    ])
    if splits:
        train, test = splits.get("train", {}), splits.get("test", {})
        lines.extend([
            f"Split: `{test.get('split_method') or 'not recorded'}`. "
            f"Training: **{fmt(train.get('rows'), ',.0f')}** observations; "
            f"test: **{fmt(test.get('rows'), ',.0f')}** observations "
            f"({fmt(benchmarks[0].get('test_dates'), ',.0f') if benchmarks else '—'} collection dates).",
            "",
        ])
    if selected:
        method = selection.get("selected_by")
        reason = (
            "selected by MAE on earlier validation windows"
            if method == "expanding_development_dates"
            else "used as the predefined default because there were too few development dates"
            if method == "median_default_insufficient_development_dates"
            else "reported in the model selection output"
        )
        lines.extend([f"**{selected_label}** was {reason}. "
                      "The final holdout was not used to choose the model.", ""])
    if benchmarks:
        lines += table(("Model", "MAE (min)", "RMSE (min)", "R²", "Bias (min)"), [
            (label(row.get("model")), fmt(row.get("mae")), fmt(row.get("rmse")),
             fmt(row.get("r2")), fmt(row.get("mean_error_pred_minus_target")))
            for row in benchmarks
        ])
        lines.extend(["Lower MAE and RMSE are better. Negative bias means underprediction; "
                      "R² can be negative.", ""])
    if "12_regression_model_mae.png" in names:
        lines.extend(["![Holdout model MAE](figures/12_regression_model_mae.png)", ""])
    lines.extend(["### Against the baselines", "",
                  "Differences are model minus reference: negative favours the model. An interval "
                  "crossing zero does not establish a clear difference. Intervals resample whole "
                  "collection dates, are exploratory and are omitted below five test dates.", ""])
    lines += paired_section(baselines)
    lines.extend([
        "## Does weather add predictive information?", "",
        "The random forests use the same test rows and settings. One model omits the MeteoSwiss "
        "features. This compares predictive usefulness, not the causal effect of weather.", "",
    ])
    lines += paired_section(weather)
    lines.extend(["## Stability across later periods", ""])
    if validation:
        by_fold = {}
        for row in validation:
            by_fold.setdefault(row.get("fold"), {})[row.get("model")] = row
        display = []
        for fold, models in by_fold.items():
            row = models.get(selected) or models.get("median_baseline") or next(iter(models.values()))
            display.append((
                fold, row.get("train_last_date"),
                f"{row.get('validation_first_date')} to {row.get('validation_last_date')}",
                fmt(row.get("validation_rows"), ",.0f"), fmt(models.get(selected, {}).get("mae")),
                fmt(models.get("group_median", {}).get("mae")),
            ))
        lines.extend(["Expanding windows use earlier data only. The final holdout is separate.", ""])
        lines += table(("Window", "Training through", "Validation dates", "Rows",
                        f"{selected_label} MAE", "Group median MAE"), display)
    else:
        lines.extend(["No eligible development windows were reported. Do not infer temporal stability "
                      "from the holdout alone.", ""])
    lines.extend(["## What the data can tell us", ""])
    for key, title in (("operational_factors", "City and mode"), ("weather", "Weather associations")):
        if finding := findings.get(key):
            lines.append(f"- **{title}:** {finding.get('finding')}. {finding.get('detail')}.")
    lines.extend([
        "", "These are exploratory comparisons. A weather correlation need not improve prediction, "
        "and a subgroup's prediction error is not a measure of an effect in that subgroup.", "",
        "## Evidence and graphics", "",
    ])
    for relative, title in (
        ("model/final_results_summary.md", "Presentation summary"),
        ("tables/data_integration_report.csv", "Data integration audit"),
        ("tables/model_holdout_benchmarks.csv", "Full holdout metrics"),
        ("tables/model_paired_comparisons.csv", "Full paired comparisons"),
        ("tables/model_temporal_validation.csv", "All temporal validation results"),
        ("tables/model_metrics_by_city.csv", "Prediction errors by city"),
        ("tables/model_metrics_by_mode.csv", "Prediction errors by mode"),
        ("tables/model_metrics_by_day_period.csv", "Prediction errors by time of day"),
        ("tables/model_holdout_coverage.csv", "Holdout coverage and unseen categories"),
        ("tables/stats_group_tests.csv", "Group tests and effect sizes"),
        ("tables/stats_weather_correlations.csv", "Weather correlations"),
        ("run_manifest.json", "Run manifest"),
    ):
        if (root / "results" / relative).is_file():
            lines.append(f"- [{title}]({relative})")
    if "20_geographic_delay_map.png" in names:
        lines.extend(["", "### Geographic overview", "",
                      "![Predicted delays by hub](figures/20_geographic_delay_map.png)", ""])
    if figures:
        lines.extend(["", "### All graphics from this run", ""])
        for figure in figures:
            lines.append(f"- [{figure.stem.replace('_', ' ')}](figures/{figure.name})")
    return "\n".join(lines).rstrip() + "\n"
