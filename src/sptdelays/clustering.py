from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .settings import PATHS, load_settings

plt.switch_backend("Agg")


def _cluster_profiles(profiles: pd.DataFrame, feature_cols: list[str], seed: int) -> tuple:
    """Exclude unusable features and never request more clusters than distinct profiles."""
    values = profiles[feature_cols].replace([np.inf, -np.inf], np.nan)
    usable = [col for col in feature_cols if values[col].nunique(dropna=True) > 1]
    if len(profiles) < 3 or not usable:
        raise ValueError(
            "K-means needs at least three stations and a non-constant profile feature."
        )
    values = values[usable].fillna(values[usable].median())
    scaled = StandardScaler().fit_transform(values)
    distinct_profiles = len(np.unique(scaled, axis=0))
    maximum_k = min(6, len(profiles) - 1, distinct_profiles)
    if maximum_k < 2:
        raise ValueError(
            "Station profiles are identical after preparation; k-means is not informative."
        )
    scores: list[dict] = []
    fitted_labels: dict[int, np.ndarray] = {}
    for k in range(2, maximum_k + 1):
        labels = KMeans(n_clusters=k, n_init=50, random_state=seed).fit_predict(scaled)
        actual_k = len(np.unique(labels))
        if actual_k < 2 or actual_k >= len(profiles):
            continue
        fitted_labels[k] = labels
        scores.append({"k": k, "silhouette": silhouette_score(scaled, labels)})
    if not scores:
        raise ValueError("No non-degenerate k-means partition can be evaluated.")
    score_table = pd.DataFrame(scores).sort_values(["silhouette", "k"], ascending=[False, True])
    best_k = int(score_table.iloc[0]["k"])
    # One varying feature can still be clustered; pad the visualization's second axis with zero.
    n_components = min(2, scaled.shape[1])
    coordinates = PCA(n_components=n_components, random_state=seed).fit_transform(scaled)
    if n_components == 1:
        coordinates = np.column_stack([coordinates[:, 0], np.zeros(len(profiles))])
    return fitted_labels[best_k], score_table, coordinates, usable


def run_clustering() -> None:
    PATHS.ensure()
    settings = load_settings()
    data = pd.read_csv(PATHS.processed / "model_data.csv", dtype={"station_id": "string"})
    profiles = (
        data.groupby(
            ["station_id", "station_name", "region", "latitude", "longitude"], dropna=False
        )
        .agg(
            observations=("observation_id", "size"),
            mean_delay=("delay_minutes", "mean"),
            median_delay=("delay_minutes", "median"),
            p90_delay=("delay_minutes", lambda values: values.quantile(0.90)),
            delayed_5_rate=("is_delayed_5", "mean"),
            mean_precipitation=("precipitation", "mean"),
            mean_wind=("wind_speed_10m", "mean"),
        )
        .reset_index()
        .dropna(subset=["mean_delay", "p90_delay", "delayed_5_rate"])
    )
    feature_cols = [
        "mean_delay",
        "median_delay",
        "p90_delay",
        "delayed_5_rate",
        "mean_precipitation",
        "mean_wind",
    ]
    labels, score_table, coordinates, used_features = _cluster_profiles(
        profiles, feature_cols, settings["random_seed"]
    )
    best_k = len(np.unique(labels))
    profiles["cluster"] = labels
    profiles["small_sample"] = profiles["observations"] < 30
    profiles["pca_1"], profiles["pca_2"] = coordinates[:, 0], coordinates[:, 1]
    profiles.to_csv(PATHS.tables / "station_clusters.csv", index=False)
    score_table.to_csv(PATHS.tables / "kmeans_silhouette.csv", index=False)
    profiles.groupby("cluster")[used_features].mean().to_csv(PATHS.tables / "cluster_profiles.csv")
    (PATHS.tables / "clustering_specification.json").write_text(
        json.dumps(
            {
                "best_k": best_k,
                "stations": len(profiles),
                "features": used_features,
                "excluded_constant_or_missing_features": [
                    col for col in feature_cols if col not in used_features
                ],
                "preprocessing": "Station-level median imputation and standardization; descriptive full-sample clustering.",
                "caveat": "Exploratory clusters, not causal or externally validated. Unequal station counts and correlated delay features influence the result; small_sample flags fewer than 30 calls.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    plt.figure(figsize=(8, 6))
    for cluster, group in profiles.groupby("cluster"):
        plt.scatter(group["pca_1"], group["pca_2"], label=f"Cluster {cluster}", s=60)
    for _, row in profiles.iterrows():
        plt.annotate(row["station_name"], (row["pca_1"], row["pca_2"]), fontsize=7, alpha=0.8)
    plt.xlabel("PCA component 1")
    plt.ylabel("PCA component 2")
    plt.title(f"Station delay profiles: k-means (k={best_k})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PATHS.figures / "06_station_clusters.png", dpi=180, bbox_inches="tight")
    plt.close()
    print(f"k-means completed with k={best_k}")
