#!/usr/bin/env python3
from pathlib import Path
from textwrap import fill

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.transforms import Bbox

DATASET_PATH = Path("data/processed/analysis_dataset.csv")
COORDINATE_PATH = Path("data/reference/hub_coordinates.csv")
TABLE_DIR = Path("results/tables")
FIGURE_DIR = Path("results/figures")

def load_inputs(dataset_path=DATASET_PATH, coordinate_path=COORDINATE_PATH):
    if not dataset_path.exists():
        raise FileNotFoundError(f"Missing {dataset_path}; run src/build_dataset.py first.")
    if not coordinate_path.exists():
        raise FileNotFoundError(f"Missing {coordinate_path}.")
    data = pd.read_csv(dataset_path)
    coords = pd.read_csv(coordinate_path)
    for col in ["predicted_delay_minutes"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    for col in ["latitude", "longitude"]:
        coords[col] = pd.to_numeric(coords[col], errors="coerce")
    return data, coords

def build_city_summary(data, coords):
    required={"city","transport_mode","predicted_delay_minutes"}
    missing=required.difference(data.columns)
    if missing:
        raise ValueError(f"Analysis dataset missing columns: {sorted(missing)}")
    work=data.dropna(subset=["city","predicted_delay_minutes"]).copy()
    work["is_delayed_5min"]=work["predicted_delay_minutes"]>=5
    summary=(work.groupby("city",as_index=False)
        .agg(observations=("predicted_delay_minutes","size"),
             mean_predicted_delay_min=("predicted_delay_minutes","mean"),
             median_predicted_delay_min=("predicted_delay_minutes","median"),
             p90_predicted_delay_min=("predicted_delay_minutes",lambda x:x.quantile(.90)),
             delayed_5min_share_pct=("is_delayed_5min",lambda x:100*x.mean()),
             transport_modes=("transport_mode",lambda x:", ".join(sorted(x.dropna().astype(str).unique())))))
    out=summary.merge(coords,on="city",how="left",validate="one_to_one")
    if out[["latitude","longitude"]].isna().any(axis=None):
        bad=out.loc[out[["latitude","longitude"]].isna().any(axis=1),"city"].tolist()
        raise ValueError(f"Missing coordinates for: {bad}")
    nums=["mean_predicted_delay_min","median_predicted_delay_min","p90_predicted_delay_min","delayed_5min_share_pct"]
    out[nums]=out[nums].round(3)
    return out.sort_values("mean_predicted_delay_min",ascending=False).reset_index(drop=True)

def _place_hub_labels(ax, hubs, sizes):
    """Measure the final text and bubbles in display pixels, after layout is fixed."""
    renderer = ax.figure.canvas.get_renderer()
    to_pixels = renderer.points_to_pixels
    plot = ax.bbox.padded(-to_pixels(5))
    bubbles = []
    for hub, size in zip(hubs, sizes):
        x, y = ax.transData.transform((hub.longitude, hub.latitude))
        radius = to_pixels(np.sqrt(size) / 2 + 0.35)  # Marker radius and half the edge stroke.
        bubbles.append(Bbox.from_extents(x - radius, y - radius, x + radius, y + radius))

    directions = ((1, 1), (-1, 1), (1, -1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1))
    options = []
    for hub, size in zip(hubs, sizes):
        annotation = ax.annotate(
            f"{hub.city}\n{hub.mean_predicted_delay_min:.2f} min",
            (hub.longitude, hub.latitude),
            xytext=(0, 0), textcoords="offset points",
            fontsize=9, zorder=4,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2},
        )
        candidates = []
        for extra in (0, 5, 11, 18):
            gap = np.sqrt(size) / 2 + 5 + extra
            for dx, dy in directions:
                offset = (dx * gap, dy * gap)
                ha = {-1: "right", 0: "center", 1: "left"}[dx]
                va = {-1: "top", 0: "center", 1: "bottom"}[dy]
                annotation.set_position(offset)
                annotation.set_ha(ha)
                annotation.set_va(va)
                box = annotation.get_window_extent(renderer).padded(to_pixels(2))
                if not (plot.contains(box.x0, box.y0) and plot.contains(box.x1, box.y1)):
                    continue
                if any(box.overlaps(bubble) for bubble in bubbles):
                    continue
                candidates.append((offset, ha, va, box))
        options.append((annotation, candidates))

    occupied = []
    unplaced = []
    # Give the most constrained hubs first choice, then use the nearest available slot.
    for index in sorted(range(len(hubs)), key=lambda i: len(options[i][1])):
        annotation, candidates = options[index]
        for offset, ha, va, box in candidates:
            if not any(box.overlaps(other) for other in occupied):
                annotation.set_position(offset)
                annotation.set_ha(ha)
                annotation.set_va(va)
                occupied.append(box)
                break
        else:
            annotation.remove()
            unplaced.append(hubs[index])
    return unplaced


def build_geographic_delay_figure(summary):
    fig, ax = plt.subplots(figsize=(10, 7), dpi=200)
    sizes = 70 + 430 * np.sqrt(summary["observations"] / summary["observations"].max())
    sc = ax.scatter(
        summary["longitude"], summary["latitude"], s=sizes,
        c=summary["mean_predicted_delay_min"], cmap="viridis",
        alpha=.82, edgecolors="black", linewidths=.7,
    )
    ax.margins(x=.12, y=.13)
    cb = fig.colorbar(sc, ax=ax, pad=.04)
    cb.set_label("Mean predicted delay (minutes)")
    ax.set_xlabel("Longitude (WGS84)")
    ax.set_ylabel("Latitude (WGS84)")
    ax.set_title("Geographic pattern of predicted public-transport delay")
    ax.grid(alpha=.25)
    ax.set_axisbelow(True)
    fig.text(.5, .015, "Bubble size = selected observations; points = sampled central hubs.",
             ha="center", fontsize=9, color="#4b5563")
    fig.tight_layout(rect=(0, .055, 1, 1))
    fig.canvas.draw()
    unplaced = _place_hub_labels(ax, list(summary.itertuples(index=False)), sizes)
    if unplaced:
        # A separate key preserves every name even for tightly clustered/long labels.
        handles = [
            Line2D([], [], marker="o", linestyle="none", markersize=7,
                   markeredgecolor="black", markeredgewidth=.5,
                   color=sc.cmap(sc.norm(hub.mean_predicted_delay_min)),
                   label=f"{fill(hub.city, width=26)} — {hub.mean_predicted_delay_min:.2f} min"
                         f"\n({hub.longitude:.3f}°, {hub.latitude:.3f}°)")
            for hub in unplaced
        ]
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, -.015),
                   ncols=min(3, len(handles)), fontsize=8, frameon=False,
                   title="Additional hub labels (longitude, latitude)")
    return fig


def plot_geographic_delay_map(summary, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig = build_geographic_delay_figure(summary)
    try:
        fig.savefig(output_path, dpi=fig.dpi, bbox_inches="tight")
    finally:
        plt.close(fig)

def run_geographic_analysis(data, coords, table_dir=TABLE_DIR, figure_dir=FIGURE_DIR):
    summary=build_city_summary(data,coords)
    table_dir.mkdir(parents=True,exist_ok=True)
    summary.to_csv(table_dir/"geographic_city_summary.csv",index=False)
    coords.to_csv(table_dir/"geographic_hub_coordinates.csv",index=False)
    plot_geographic_delay_map(summary,figure_dir/"20_geographic_delay_map.png")
    return summary

def main():
    print("="*72); print("GEOGRAPHIC ANALYSIS"); print("="*72)
    data,coords=load_inputs()
    summary=run_geographic_analysis(data,coords)
    print(summary[["city","observations","mean_predicted_delay_min","delayed_5min_share_pct","latitude","longitude"]].to_string(index=False))
    print("\nSaved results/tables/geographic_city_summary.csv")
    print("Saved results/figures/20_geographic_delay_map.png")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
