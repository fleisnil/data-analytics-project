from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd


def normalize_station_id(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    # Swiss BPUIC IDs may contain leading zeroes or platform suffixes. Do not
    # extract arbitrary digits from unrelated identifiers such as a SLOID.
    digits = re.sub(r"\.0+$", "", text).lstrip("0")
    if not digits.isdigit():
        return text or None
    if digits.startswith("85") and len(digits) >= 7:
        return digits[:7]
    return text or None


def stable_id(parts: Iterable[object]) -> str:
    values = [None if item is None or pd.isna(item) else str(item) for item in parts]
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def parse_transport_mode(category: object) -> str:
    value = "" if category is None or pd.isna(category) else str(category).strip().upper()
    if not value:
        return "unknown"
    if value in {"BUS", "B", "NFB", "NFO", "POSTAUTO", "NIGHT BUS"} or "BUS" in value:
        return "bus"
    if value in {"TRAM", "T", "NFT"} or "TRAM" in value:
        return "tram"
    if value in {"METRO", "M", "U"} or "METRO" in value:
        return "metro"
    if value in {"SHIP", "BAT", "SCHIFF", "BOAT"} or "SCHIFF" in value:
        return "ship"
    if value in {"CABLEWAY", "FUN", "GB", "PB", "CC", "FUNI"}:
        return "cableway"
    train_tokens = {"ZUG", "TRAIN", "IC", "ICN", "IR", "IRE", "RE", "R", "S", "SN", "EC", "EN", "NJ", "TGV", "RJ", "RJX", "ICE", "PE"}
    if value in train_tokens or any(token in value.split() for token in train_tokens) or re.fullmatch(
        r"(?:IC|IR|RE|S|SN|R)\s*\d+", value
    ):
        return "train"
    return "other"


def add_time_features(frame: pd.DataFrame, time_col: str = "scheduled_time") -> pd.DataFrame:
    result = frame.copy()
    result[time_col] = pd.to_datetime(result[time_col], errors="coerce", utc=True)
    local = result[time_col].dt.tz_convert("Europe/Zurich")
    result["service_date"] = local.dt.date.astype("string")
    result["scheduled_hour"] = local.dt.hour
    result["weekday"] = local.dt.day_name()
    result["is_weekend"] = local.dt.dayofweek.ge(5).astype(int)
    result["is_peak"] = local.dt.hour.isin([6, 7, 8, 16, 17, 18]).astype(int)
    result["day_period"] = pd.cut(
        local.dt.hour,
        bins=[-1, 5, 8, 15, 18, 23],
        labels=["night", "morning_peak", "midday", "evening_peak", "evening"],
    ).astype("string")
    # Floor in UTC: the autumn DST transition contains two different 02:00
    # hours in Zurich. Flooring local wall-clock time would be ambiguous.
    result["observation_hour"] = (
        result[time_col].dt.floor("h").dt.tz_convert("Europe/Zurich")
        .dt.strftime("%Y-%m-%dT%H:00:00%z")
    )
    return result


def write_json(path: Path, payload: object, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

