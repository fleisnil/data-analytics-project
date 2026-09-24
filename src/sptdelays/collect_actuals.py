from __future__ import annotations

import csv
import html
import io
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

from .collect_stations import load_station_panel
from .http import USER_AGENT
from .settings import PATHS, load_settings
from .utils import normalize_station_id

RESOURCE_PATTERN = re.compile(
    r'href=["\']([^"\']+/download/(\d{4}-\d{2}-\d{2}_istdaten\.csv))["\']',
    re.IGNORECASE,
)


def discover_resources() -> dict[str, str]:
    settings = load_settings()
    response = requests.get(
        settings["actuals_dataset_page"],
        headers={"User-Agent": USER_AGENT},
        timeout=(10, settings["request_timeout_seconds"]),
    )
    response.raise_for_status()
    resources: dict[str, str] = {}
    for href, filename in RESOURCE_PATTERN.findall(html.unescape(response.text)):
        date = filename[:10]
        resources[date] = urljoin(response.url, href)
    if not resources:
        raise RuntimeError("No daily Actual data v2 resources were found on the dataset page.")
    return dict(sorted(resources.items(), reverse=True))


def list_resources(limit: int = 30) -> None:
    resources = discover_resources()
    for date, url in list(resources.items())[:limit]:
        print(f"{date}\t{url}")


def collect_actuals(dates: list[str]) -> list[Path]:
    resources = discover_resources()
    stations = load_station_panel()
    selected_ids = set(stations["station_id"].map(normalize_station_id).dropna())
    output_files: list[Path] = []
    for date in dates:
        if date not in resources:
            raise ValueError(f"Date {date} is not available on the current dataset page.")
        url = resources[date]
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/csv"},
            stream=True,
            timeout=(15, 180),
        )
        response.raise_for_status()
        response.raw.decode_content = True
        text_stream = io.TextIOWrapper(response.raw, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_stream, delimiter=";")
        output = PATHS.raw / "actuals_v2" / f"{date}_selected_stations.csv"
        output.parent.mkdir(parents=True, exist_ok=True)
        kept = 0
        scanned = 0
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=reader.fieldnames or [], delimiter=";")
            writer.writeheader()
            for row in reader:
                scanned += 1
                if normalize_station_id(row.get("BPUIC")) in selected_ids:
                    writer.writerow(row)
                    kept += 1
        print(f"{date}: scanned {scanned:,}, retained {kept:,} station-call rows")
        output_files.append(output)
    return output_files
