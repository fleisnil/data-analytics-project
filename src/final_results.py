#!/usr/bin/env python3
"""
Build presentation-ready result summaries from the generated analysis tables.

This script does not refit models. It reads the reproducible outputs from
EDA, statistical analysis and regression modelling and creates:
- a compact city/mode MAE-improvement figure
- a final key-findings table
- a Markdown presentation summary
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


TABLE_DIR = Path("results/tables")
FIGURE_DIR = Path("results/figures")
MODEL_DIR = Path("results/model")

BASELINE_MODEL = "median_baseline"


def read_required_csv(
    path: Path,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Required result table not found: {path}. "
            "Run the full analysis pipeline first."
        )
    return pd.read_csv(path)


def group_improvement_table(
    metrics: pd.DataFrame,
    group_column: str,
    best_model: str,
) -> pd.DataFrame:
    required = {
        group_column,
        "model",
        "observations",
        "mae",
    }
    missing = required.difference(
        metrics.columns
    )
    if missing:
        raise ValueError(
            f"Missing columns in grouped metrics: {sorted(missing)}"
        )

    baseline = (
        metrics.loc[
            metrics["model"]
            == BASELINE_MODEL,
            [
                group_column,
                "observations",
                "mae",
            ],
        ]
        .rename(
            columns={
                "observations": (
                    "observations_baseline"
                ),
                "mae": "baseline_mae",
            }
        )
    )

    selected = (
        metrics.loc[
            metrics["model"]
            == best_model,
            [
                group_column,
                "observations",
                "mae",
                "rmse",
                "r2",
            ],
        ]
        .rename(
            columns={
                "observations": (
                    "observations"
                ),
                "mae": "best_model_mae",
                "rmse": "best_model_rmse",
                "r2": "best_model_r2",
            }
        )
    )

    merged = baseline.merge(
        selected,
        on=group_column,
        how="inner",
        validate="one_to_one",
    )

    merged[
        "mae_improvement_pct"
    ] = np.where(
        merged["baseline_mae"] != 0,
        100
        * (
            merged["baseline_mae"]
            - merged["best_model_mae"]
        )
        / merged["baseline_mae"],
        np.nan,
    )

    return (
        merged[
            [
                group_column,
                "observations",
                "baseline_mae",
                "best_model_mae",
                "mae_improvement_pct",
                "best_model_rmse",
                "best_model_r2",
            ]
        ]
        .sort_values(
            "mae_improvement_pct",
            ascending=False,
        )
        .reset_index(drop=True)
    )


def build_key_findings(
    integration: pd.DataFrame,
    eda_overview: pd.DataFrame,
    group_tests: pd.DataFrame,
    weather_corr: pd.DataFrame,
    wet_dry: pd.DataFrame,
    model_metrics: pd.DataFrame,
    model_selection: pd.DataFrame,
) -> pd.DataFrame:
    integration_map = dict(
        zip(
            integration["metric"],
            integration["value"],
        )
    )
    eda_map = dict(
        zip(
            eda_overview["metric"],
            eda_overview["value"],
        )
    )

    best_model = str(
        model_selection.loc[
            0,
            "best_model",
        ]
    )
    best_row = (
        model_metrics.loc[
            model_metrics["model"]
            == best_model
        ].iloc[0]
    )
    baseline_row = (
        model_metrics.loc[
            model_metrics["model"]
            == BASELINE_MODEL
        ].iloc[0]
    )

    transport_test = (
        group_tests.loc[
            group_tests[
                "group_variable"
            ]
            == "transport_mode"
        ].iloc[0]
    )
    city_test = (
        group_tests.loc[
            group_tests[
                "group_variable"
            ]
            == "city"
        ].iloc[0]
    )

    within_city = weather_corr.loc[
        weather_corr["scope"]
        == "within_city_centered"
    ].copy()

    strongest_weather = (
        within_city.assign(
            abs_rho=within_city[
                "spearman_rho"
            ].abs()
        )
        .sort_values(
            "abs_rho",
            ascending=False,
        )
        .iloc[0]
    )

    precip = within_city.loc[
        within_city[
            "weather_variable"
        ]
        == "precipitation_mm_10min"
    ]
    precip_row = (
        precip.iloc[0]
        if not precip.empty
        else None
    )

    wet_p = (
        float(
            wet_dry.loc[
                0,
                "p_value",
            ]
        )
        if not wet_dry.empty
        else np.nan
    )

    rows = [
        {
            "topic": "sample",
            "finding": (
                f"{int(float(integration_map['selected_unique_journey_stops']))} "
                "selected journey/stop observations"
            ),
            "detail": (
                f"Weather match rate "
                f"{float(integration_map['weather_match_rate_pct']):.2f}%"
            ),
        },
        {
            "topic": "delay_distribution",
            "finding": (
                f"Mean predicted delay "
                f"{float(eda_map['delay_mean_min']):.3f} min; "
                f"median {float(eda_map['delay_median_min']):.1f} min"
            ),
            "detail": (
                f"Only {float(eda_map['delayed_5min_share_pct']):.2f}% "
                "of observations are >=5 min"
            ),
        },
        {
            "topic": "operational_factors",
            "finding": (
                "Transport mode shows the stronger group effect"
            ),
            "detail": (
                f"Kruskal-Wallis epsilon^2="
                f"{float(transport_test['epsilon_squared']):.3f}; "
                f"city epsilon^2={float(city_test['epsilon_squared']):.3f}"
            ),
        },
        {
            "topic": "weather",
            "finding": (
                f"Strongest within-city weather correlation: "
                f"{strongest_weather['weather_variable']} "
                f"(rho={float(strongest_weather['spearman_rho']):.3f})"
            ),
            "detail": (
                (
                    f"Precipitation rho="
                    f"{float(precip_row['spearman_rho']):.3f}; "
                    f"p={float(precip_row['p_value']):.3f}; "
                    f"wet-vs-dry p={wet_p:.3f}"
                )
                if precip_row is not None
                else (
                    f"Wet-vs-dry p={wet_p:.3f}"
                )
            ),
        },
        {
            "topic": "model",
            "finding": (
                f"{best_model} has the lowest MAE: "
                f"{float(best_row['mae']):.4f} min"
            ),
            "detail": (
                f"{float(model_selection.loc[0, 'mae_improvement_vs_baseline_pct']):.2f}% "
                f"MAE improvement vs baseline; "
                f"R2={float(best_row['r2']):.4f}, "
                f"baseline RMSE={float(baseline_row['rmse']):.4f}, "
                f"best-model RMSE={float(best_row['rmse']):.4f}"
            ),
        },
    ]

    return pd.DataFrame(rows)


def plot_group_improvements(
    city_table: pd.DataFrame,
    mode_table: pd.DataFrame,
    figure_dir: Path,
) -> None:
    figure_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    fig, axes = plt.subplots(
        1,
        2,
        figsize=(13, 5.5),
    )

    city_plot = city_table.sort_values(
        "mae_improvement_pct",
        ascending=True,
    )
    axes[0].barh(
        city_plot["city"],
        city_plot[
            "mae_improvement_pct"
        ],
    )
    axes[0].axvline(
        0,
        linewidth=1,
    )
    axes[0].set_xlabel(
        "MAE improvement vs median baseline (%)"
    )
    axes[0].set_ylabel("Region")
    axes[0].set_title(
        "By region"
    )

    for i, value in enumerate(
        city_plot[
            "mae_improvement_pct"
        ]
    ):
        axes[0].text(
            value + 0.3,
            i,
            f"{value:.1f}%",
            va="center",
        )

    mode_plot = mode_table.sort_values(
        "mae_improvement_pct",
        ascending=True,
    )
    axes[1].barh(
        mode_plot[
            "transport_mode"
        ],
        mode_plot[
            "mae_improvement_pct"
        ],
    )
    axes[1].axvline(
        0,
        linewidth=1,
    )
    axes[1].set_xlabel(
        "MAE improvement vs median baseline (%)"
    )
    axes[1].set_ylabel(
        "Transport mode"
    )
    axes[1].set_title(
        "By transport mode"
    )

    for i, value in enumerate(
        mode_plot[
            "mae_improvement_pct"
        ]
    ):
        axes[1].text(
            value + 0.3,
            i,
            f"{value:.1f}%",
            va="center",
        )

    fig.suptitle(
        "Gradient boosting improvement over the median baseline"
    )
    fig.tight_layout()
    fig.savefig(
        figure_dir
        / "16_mae_improvement_by_city_and_mode.png",
        dpi=200,
        bbox_inches="tight",
    )
    plt.close(fig)


def build_summary_markdown(
    key_findings: pd.DataFrame,
    city_table: pd.DataFrame,
    mode_table: pd.DataFrame,
    importance: pd.DataFrame,
    model_selection: pd.DataFrame,
) -> str:
    best_model = str(
        model_selection.loc[
            0,
            "best_model",
        ]
    )

    top_cities = city_table.head(
        4
    )
    top_city_text = ", ".join(
        f"{row['city']} ({row['mae_improvement_pct']:.1f}%)"
        for _, row in top_cities.iterrows()
    )

    mode_text = ", ".join(
        f"{row['transport_mode']} ({row['mae_improvement_pct']:.1f}%)"
        for _, row in mode_table.iterrows()
    )

    if importance.empty:
        importance_text = (
            "No model-based feature importance is interpreted because "
            "the baseline remains the best-MAE model."
        )
    else:
        top_features = importance.head(
            4
        )
        importance_text = ", ".join(
            f"{row['feature']} ({row['importance_mae_increase']:.5f})"
            for _, row in top_features.iterrows()
        )

    findings_lines = "\n".join(
        f"- **{row['topic']}**: {row['finding']}. {row['detail']}."
        for _, row in key_findings.iterrows()
    )

    return f"""# Final Results Summary

## Research question

Which operational, temporal and weather-related factors are associated with public transport delays in Switzerland, and how do these associations differ across regions and transport modes?

## Key evidence

{findings_lines}

## Model interpretation

The best model by the pre-defined primary metric MAE is **{best_model}**. Its improvement is not uniform across the sample.

Largest regional MAE improvements: {top_city_text}.

MAE improvement by transport mode: {mode_text}.

Top permutation-importance features: {importance_text}.

## Presentation conclusion

Operational and regional factors are more informative than the observed weather variables for explaining and predicting short-term OJP departure-delay estimates. The best regression model improves typical absolute prediction error relative to a simple median baseline, but RMSE/R2 results show that larger and unusual delays remain difficult to predict.

Weather variables show some weak statistical associations, but they add little incremental predictive value in the best model. Precipitation in particular is not supported as an important factor in the current sample.

Results describe associations in the observed central-hub sample. They do not establish causal effects, and OJP EstimatedTime is a real-time estimate rather than a realised final delay.
"""


def generate_final_results(
    table_dir: Path = TABLE_DIR,
    figure_dir: Path = FIGURE_DIR,
    model_dir: Path = MODEL_DIR,
) -> dict[str, pd.DataFrame]:
    model_metrics = read_required_csv(
        table_dir
        / "model_regression_metrics.csv"
    )
    model_selection = read_required_csv(
        table_dir
        / "model_selection_summary.csv"
    )
    city_metrics = read_required_csv(
        table_dir
        / "model_metrics_by_city.csv"
    )
    mode_metrics = read_required_csv(
        table_dir
        / "model_metrics_by_mode.csv"
    )
    importance = read_required_csv(
        table_dir
        / "model_best_permutation_importance.csv"
    )
    integration = read_required_csv(
        table_dir
        / "data_integration_report.csv"
    )
    eda_overview = read_required_csv(
        table_dir
        / "eda_overview.csv"
    )
    group_tests = read_required_csv(
        table_dir
        / "stats_group_tests.csv"
    )
    weather_corr = read_required_csv(
        table_dir
        / "stats_weather_correlations.csv"
    )
    wet_dry = read_required_csv(
        table_dir
        / "stats_wet_dry.csv"
    )

    best_model = str(
        model_selection.loc[
            0,
            "best_model",
        ]
    )

    city_improvement = (
        group_improvement_table(
            city_metrics,
            "city",
            best_model,
        )
    )
    mode_improvement = (
        group_improvement_table(
            mode_metrics,
            "transport_mode",
            best_model,
        )
    )

    key_findings = build_key_findings(
        integration,
        eda_overview,
        group_tests,
        weather_corr,
        wet_dry,
        model_metrics,
        model_selection,
    )

    plot_group_improvements(
        city_improvement,
        mode_improvement,
        figure_dir,
    )

    table_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    city_improvement.to_csv(
        table_dir
        / "final_model_improvement_by_city.csv",
        index=False,
    )
    mode_improvement.to_csv(
        table_dir
        / "final_model_improvement_by_mode.csv",
        index=False,
    )
    key_findings.to_csv(
        table_dir
        / "final_key_findings.csv",
        index=False,
    )

    summary = build_summary_markdown(
        key_findings,
        city_improvement,
        mode_improvement,
        importance,
        model_selection,
    )
    (
        model_dir
        / "final_results_summary.md"
    ).write_text(
        summary,
        encoding="utf-8",
    )

    return {
        "final_key_findings": (
            key_findings
        ),
        "final_model_improvement_by_city": (
            city_improvement
        ),
        "final_model_improvement_by_mode": (
            mode_improvement
        ),
    }


def main() -> int:
    print("=" * 72)
    print("FINAL RESULTS SYNTHESIS")
    print("=" * 72)

    outputs = generate_final_results()

    print(
        "\nKey findings:"
    )
    print(
        outputs[
            "final_key_findings"
        ].to_string(
            index=False
        )
    )

    print(
        "\nMAE improvement by city:"
    )
    print(
        outputs[
            "final_model_improvement_by_city"
        ][
            [
                "city",
                "observations",
                "mae_improvement_pct",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        "\nMAE improvement by mode:"
    )
    print(
        outputs[
            "final_model_improvement_by_mode"
        ][
            [
                "transport_mode",
                "observations",
                "mae_improvement_pct",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        "\nPresentation-ready outputs:"
    )
    print(
        "  results/figures/16_mae_improvement_by_city_and_mode.png"
    )
    print(
        "  results/tables/final_key_findings.csv"
    )
    print(
        "  results/model/final_results_summary.md"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
