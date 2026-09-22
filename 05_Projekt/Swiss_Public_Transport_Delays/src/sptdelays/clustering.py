from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .settings import PATHS, load_settings

plt.switch_backend("Agg")


def run_clustering() -> None:
    settings = load_settings()
    data = pd.read_csv(PATHS.processed / "model_data.csv", dtype={"station_id": "string"})
    profiles = (
        data.groupby(["station_id", "station_name", "region", "latitude", "longitude"], dropna=False)
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
    if len(profiles) < 3:
        raise ValueError("At least three station profiles are needed for k-means.")
    feature_cols = ["mean_delay", "median_delay", "p90_delay", "delayed_5_rate", "mean_precipitation", "mean_wind"]
    values = profiles[feature_cols].fillna(profiles[feature_cols].median())
    scaled = StandardScaler().fit_transform(values)
    scores: list[dict] = []
    candidates = range(2, min(6, len(profiles) - 1) + 1)
    for k in candidates:
        labels = KMeans(n_clusters=k, n_init=20, random_state=settings["random_seed"]).fit_predict(scaled)
        scores.append({"k": k, "silhouette": silhouette_score(scaled, labels)})
    score_table = pd.DataFrame(scores)
    best_k = int(score_table.sort_values("silhouette", ascending=False).iloc[0]["k"])
    model = KMeans(n_clusters=best_k, n_init=50, random_state=settings["random_seed"])
    profiles["cluster"] = model.fit_predict(scaled)
    profiles.to_csv(PATHS.tables / "station_clusters.csv", index=False)
    score_table.to_csv(PATHS.tables / "kmeans_silhouette.csv", index=False)
    coordinates = PCA(n_components=2, random_state=settings["random_seed"]).fit_transform(scaled)
    profiles["pca_1"], profiles["pca_2"] = coordinates[:, 0], coordinates[:, 1]
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
