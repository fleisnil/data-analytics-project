#!/usr/bin/env python3
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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

def plot_geographic_delay_map(summary, output_path):
    output_path.parent.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(10,7))
    sizes=70+430*np.sqrt(summary["observations"]/summary["observations"].max())
    sc=ax.scatter(summary["longitude"],summary["latitude"],s=sizes,
                  c=summary["mean_predicted_delay_min"],cmap="viridis",
                  alpha=.82,edgecolors="black",linewidths=.7)
    for _,r in summary.iterrows():
        ax.annotate(f"{r['city']}\n{r['mean_predicted_delay_min']:.2f} min",
                    (r["longitude"],r["latitude"]),xytext=(6,6),
                    textcoords="offset points",fontsize=9)
    cb=fig.colorbar(sc,ax=ax,pad=.02)
    cb.set_label("Mean predicted delay (minutes)")
    ax.set_xlabel("Longitude (WGS84)")
    ax.set_ylabel("Latitude (WGS84)")
    ax.set_title("Geographic pattern of predicted public-transport delay")
    ax.grid(alpha=.25)
    ax.text(.01,.01,"Bubble size = selected observations; points = eight sampled central hubs.",
            transform=ax.transAxes,fontsize=9,va="bottom")
    fig.tight_layout()
    fig.savefig(output_path,dpi=200,bbox_inches="tight")
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
