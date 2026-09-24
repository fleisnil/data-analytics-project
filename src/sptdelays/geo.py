from __future__ import annotations

from html import escape
from pathlib import Path

import folium
import pandas as pd
from branca.colormap import linear

from .settings import PATHS


def create_map() -> Path:
    PATHS.ensure()
    data = pd.read_csv(PATHS.processed / "model_data.csv", dtype={"station_id": "string"})
    stations = (
        data.groupby(["station_id", "station_name", "region", "latitude", "longitude"], dropna=False)
        .agg(
            observations=("observation_id", "size"),
            mean_delay=("delay_minutes", "mean"),
            delayed_5_rate=("is_delayed_5", "mean"),
        )
        .reset_index()
        .dropna(subset=["latitude", "longitude"])
    )
    if stations.empty:
        raise ValueError("No station coordinates are available for the map.")
    centre = [stations["latitude"].mean(), stations["longitude"].mean()]
    map_object = folium.Map(location=centre, zoom_start=8, tiles="OpenStreetMap")
    maximum = max(1.0, stations["mean_delay"].max())
    colours = linear.YlOrRd_09.scale(0, maximum)
    colours.caption = "Mean reported delay (minutes)"
    colours.add_to(map_object)
    for _, row in stations.iterrows():
        popup = (
            f"<b>{escape(str(row['station_name']))}</b><br>Region: {escape(str(row['region']))}<br>"
            f"Observations: {int(row['observations'])}<br>Mean delay: {row['mean_delay']:.2f} min<br>"
            f"Delayed ≥5 min: {row['delayed_5_rate']:.1%}"
        )
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5 + min(12, row["observations"] ** 0.5 / 3),
            color=colours(row["mean_delay"]),
            fill=True,
            fill_opacity=0.75,
            popup=folium.Popup(popup, max_width=300),
            tooltip=escape(str(row["station_name"])),
        ).add_to(map_object)
    output = PATHS.root / "reports" / "station_delay_map.html"
    map_object.save(output)
    stations.to_csv(PATHS.tables / "station_geography_summary.csv", index=False)
    print(f"Interactive map created: {output}")
    return output
