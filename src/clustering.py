#!/usr/bin/env python3
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

DATASET_PATH=Path("data/processed/analysis_dataset.csv")
TABLE_DIR=Path("results/tables")
FIGURE_DIR=Path("results/figures")
MODEL_DIR=Path("results/model")
RANDOM_STATE=42
FEATURES=["predicted_delay_minutes","temperature_c","precipitation_mm_10min",
          "relative_humidity_pct","wind_speed_kmh_10min","wind_gust_kmh","station_pressure_hpa"]

def load_dataset(path=DATASET_PATH):
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}; run src/build_dataset.py first.")
    return pd.read_csv(path)

def prepare_clustering_features(df):
    missing=[c for c in FEATURES+["hour"] if c not in df.columns]
    if missing: raise ValueError(f"Dataset missing clustering columns: {missing}")
    work=df.copy()
    for c in FEATURES+["hour"]: work[c]=pd.to_numeric(work[c],errors="coerce")
    work=work.dropna(subset=["predicted_delay_minutes","hour"]).copy()
    radians=2*np.pi*work["hour"]/24
    work["hour_sin"]=np.sin(radians); work["hour_cos"]=np.cos(radians)
    feature_cols=["predicted_delay_minutes","hour_sin","hour_cos"]+FEATURES[1:]
    x=SimpleImputer(strategy="median").fit_transform(work[feature_cols])
    x=StandardScaler().fit_transform(x)
    return work.reset_index(drop=True),x,feature_cols

def select_k(x,candidates=range(2,7)):
    rows=[]
    for k in candidates:
        if k>=len(x): continue
        model=KMeans(n_clusters=k,n_init=20,random_state=RANDOM_STATE)
        labels=model.fit_predict(x)
        score=silhouette_score(x,labels,sample_size=min(3000,len(x)),random_state=RANDOM_STATE)
        rows.append({"k":k,"silhouette_score":score,"inertia":model.inertia_})
    if not rows: raise ValueError("Not enough observations for k-means.")
    scores=pd.DataFrame(rows)
    best_k=int(scores.loc[scores["silhouette_score"].idxmax(),"k"])
    scores[["silhouette_score","inertia"]]=scores[["silhouette_score","inertia"]].round(5)
    return scores,best_k

def fit_kmeans(x,k):
    model=KMeans(n_clusters=k,n_init=30,random_state=RANDOM_STATE)
    return model,model.fit_predict(x)

def _mode(s):
    s=s.dropna().astype(str)
    return "" if s.empty else s.value_counts().index[0]

def build_cluster_profiles(assignments):
    a=assignments.copy()
    a["is_delayed_5min"]=a["predicted_delay_minutes"]>=5
    profiles=(a.groupby("cluster",as_index=False)
      .agg(observations=("predicted_delay_minutes","size"),
           mean_delay_min=("predicted_delay_minutes","mean"),
           median_delay_min=("predicted_delay_minutes","median"),
           p90_delay_min=("predicted_delay_minutes",lambda x:x.quantile(.90)),
           delayed_5min_share_pct=("is_delayed_5min",lambda x:100*x.mean()),
           mean_temperature_c=("temperature_c","mean"),
           mean_precipitation_mm_10min=("precipitation_mm_10min","mean"),
           mean_relative_humidity_pct=("relative_humidity_pct","mean"),
           mean_wind_speed_kmh=("wind_speed_kmh_10min","mean"),
           dominant_city=("city",_mode),
           dominant_transport_mode=("transport_mode",_mode)))
    nums=[c for c in profiles.columns if c.startswith("mean_") or c.startswith("median_") or c.startswith("p90_") or c=="delayed_5min_share_pct"]
    profiles[nums]=profiles[nums].round(3)
    return profiles.sort_values("mean_delay_min",ascending=False).reset_index(drop=True)

def build_composition(assignments):
    out=(assignments.groupby(["cluster","city","transport_mode"],dropna=False)
         .size().reset_index(name="observations"))
    totals=out.groupby("cluster")["observations"].transform("sum")
    out["cluster_share_pct"]=(100*out["observations"]/totals).round(2)
    return out.sort_values(["cluster","observations"],ascending=[True,False])

def save_figures(scores,assignments,profiles,x,figure_dir):
    figure_dir.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(7,5))
    ax.plot(scores["k"],scores["silhouette_score"],marker="o")
    ax.set(xlabel="Number of clusters (k)",ylabel="Silhouette score",title="K-means model selection")
    ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(figure_dir/"17_kmeans_silhouette.png",dpi=200); plt.close(fig)
    pca=PCA(n_components=2,random_state=RANDOM_STATE).fit_transform(x)
    fig,ax=plt.subplots(figsize=(8,6))
    sc=ax.scatter(pca[:,0],pca[:,1],c=assignments["cluster"],cmap="tab10",s=16,alpha=.55)
    ax.set(xlabel="PCA component 1",ylabel="PCA component 2",title="K-means clusters projected with PCA")
    ax.legend(*sc.legend_elements(),title="Cluster"); fig.tight_layout(); fig.savefig(figure_dir/"18_kmeans_pca_clusters.png",dpi=200); plt.close(fig)
    p=profiles.sort_values("mean_delay_min")
    fig,ax=plt.subplots(figsize=(8,5)); ax.barh(p["cluster"].astype(str),p["mean_delay_min"])
    ax.set(xlabel="Mean predicted delay (minutes)",ylabel="Cluster",title="Delay profile of k-means clusters")
    fig.tight_layout(); fig.savefig(figure_dir/"19_kmeans_cluster_delay_profiles.png",dpi=200); plt.close(fig)

def run_clustering(df,table_dir=TABLE_DIR,figure_dir=FIGURE_DIR,model_dir=MODEL_DIR):
    work,x,features=prepare_clustering_features(df)
    scores,best_k=select_k(x)
    model,labels=fit_kmeans(x,best_k)
    keep=[c for c in ["collection_timestamp","city","transport_mode","station_type","predicted_delay_minutes","hour"]+FEATURES[1:] if c in work.columns]
    assignments=work[keep].copy(); assignments.insert(0,"cluster",labels)
    profiles=build_cluster_profiles(assignments); composition=build_composition(assignments)
    table_dir.mkdir(parents=True,exist_ok=True); model_dir.mkdir(parents=True,exist_ok=True)
    scores.to_csv(table_dir/"clustering_silhouette_scores.csv",index=False)
    profiles.to_csv(table_dir/"clustering_profiles.csv",index=False)
    composition.to_csv(table_dir/"clustering_city_mode_composition.csv",index=False)
    pd.DataFrame({"feature":features}).to_csv(table_dir/"clustering_features.csv",index=False)
    assignments.to_csv(model_dir/"kmeans_cluster_assignments.csv",index=False)
    save_figures(scores,assignments,profiles,x,figure_dir)
    return scores,best_k,profiles

def main():
    print("="*72); print("K-MEANS CLUSTERING"); print("="*72)
    scores,best_k,profiles=run_clustering(load_dataset())
    print("\nSilhouette scores:"); print(scores.to_string(index=False))
    print(f"\nSelected k: {best_k}")
    print("\nCluster profiles:"); print(profiles.to_string(index=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
