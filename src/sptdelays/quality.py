"""Separate structural data checks from the group's final study coverage targets."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from .settings import PATHS, load_settings


def assess_data(frame: pd.DataFrame, settings: dict) -> dict:
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str, severity: str = "error") -> None:
        checks.append({"check": name, "passed": bool(passed), "severity": severity,
                       "detail": detail})

    required = {"observation_id", "station_id", "scheduled_time", "service_date", "region",
                "transport_mode", "day_period", "delay_minutes", "is_delayed_5",
                "observation_hour"}
    missing = sorted(required - set(frame.columns))
    check("required_columns", not missing, f"Missing columns: {missing}")
    check("nonempty_data", not frame.empty, f"Rows: {len(frame)}")
    coverage: dict = {"rows": len(frame)}
    if not missing and not frame.empty:
        keys = frame["observation_id"]
        check("unique_observation_keys", keys.notna().all() and keys.is_unique,
              f"Duplicate keys: {keys.duplicated().sum()}; missing keys: {keys.isna().sum()}")
        delay = pd.to_numeric(frame["delay_minutes"], errors="coerce")
        valid_delay = np.isfinite(delay) & delay.between(
            0, settings["maximum_plausible_delay_minutes"]
        )
        check("valid_delay_target", valid_delay.all(),
              f"Missing/nonfinite/out-of-range targets: {(~valid_delay).sum()}")
        times = pd.to_datetime(frame["scheduled_time"], errors="coerce", utc=True)
        hours = pd.to_datetime(frame["observation_hour"], errors="coerce", utc=True)
        check("valid_timestamps", times.notna().all() and hours.notna().all(),
              f"Invalid scheduled times: {times.isna().sum()}; hours: {hours.isna().sum()}")
        check("hour_key_matches_schedule", (times.dt.floor("h") == hours).all(),
              "Weather keys must refer to the scheduled UTC hour.")
        dates = pd.to_datetime(frame["service_date"], format="%Y-%m-%d", errors="coerce")
        check("valid_service_dates", dates.notna().all(),
              f"Invalid service dates: {dates.isna().sum()}")
        local_dates = times.dt.tz_convert(settings.get("timezone", "Europe/Zurich")).dt.date
        check("service_dates_match_local_schedule", (dates.dt.date == local_dates).all(),
              "The project service date is the local calendar date of the scheduled call.")
        check("required_groups_present", frame[["station_id", "region", "transport_mode",
                                               "day_period"]].notna().all().all(),
              "Station, region, mode and time period must be known.")
        if "is_delayed_5" in frame:
            check("delay_indicator_consistent",
                  frame["is_delayed_5"].eq(delay.ge(settings["delay_threshold_minutes"])).all(),
                  "The five-minute indicator must agree with the target.")
        unique_dates = int(dates.nunique())
        target_days = settings.get("study_target_service_days", 28)
        regions = sorted(frame["region"].dropna().astype(str).unique().tolist())
        modes = sorted(frame["transport_mode"].dropna().astype(str).unique().tolist())
        periods = sorted(frame["day_period"].dropna().astype(str).unique().tolist())
        span_days = int((dates.max() - dates.min()).days + 1) if unique_dates else 0
        missing_calendar_days = span_days - unique_dates
        region_days = frame.assign(_service_date=dates).groupby("region", observed=True)[
            "_service_date"
        ].nunique().to_dict()
        region_day_shares = {
            str(region): count / unique_dates for region, count in region_days.items()
        } if unique_dates else {}
        minimum_region_share = min(region_day_shares.values(), default=0.0)
        check("study_duration", unique_dates >= target_days,
              f"{unique_dates}/{target_days} distinct service dates; a study-design target, "
              "not a lecturer-specified minimum.", "warning")
        check("calendar_day_contiguity", missing_calendar_days == 0,
              f"{missing_calendar_days} missing calendar date(s) within the {span_days}-day observed span. "
              "A scattered set of dates is not a continuous collection window.", "warning")
        check("regional_coverage", len(regions) >= settings.get("study_target_regions", 7),
              f"Observed regions: {regions}", "warning")
        region_target = settings.get("study_target_region_day_share", 0.8)
        check("region_day_coverage", minimum_region_share >= region_target,
              f"Lowest observed region-day share: {minimum_region_share:.1%}; "
              f"project target: {region_target:.0%} of observed service dates.", "warning")
        check("weekday_and_weekend", dates.dt.dayofweek.lt(5).any()
              and dates.dt.dayofweek.ge(5).any(), "Include weekdays and weekends.", "warning")
        check("mode_comparison", len(modes) >= 2, f"Observed modes: {modes}", "warning")
        check("time_comparison", len(periods) >= settings.get("study_target_day_periods", 5),
              f"Observed periods: {periods}; inspect collection gaps as well.", "warning")
        expected_weather = settings["weather_hourly_variables"]
        missing_weather = sorted(set(expected_weather) - set(frame))
        check("weather_columns_present", not missing_weather,
              f"Missing configured weather columns: {missing_weather}")
        explicit_weather = "weather_source" in frame and frame["weather_source"].notna().any()
        check("weather_provenance", explicit_weather,
              "Weather source type is absent from the integrated rows. Older development "
              "data may predate provenance logging; collect or document it for the final run.",
              "warning")
        weather_cols = [c for c in settings["weather_hourly_variables"] if c in frame]
        weather_complete = (frame[weather_cols].notna().all(axis=1).mean()
                            if len(weather_cols) == len(settings["weather_hourly_variables"])
                            else 0.0)
        check("weather_coverage", weather_complete >= settings.get("weather_coverage_target", .95),
              f"Complete configured weather variables: {weather_complete:.1%}. "
              "This is value coverage, not merely a matched join key.", "warning")
        coverage.update({"stations": int(frame["station_id"].nunique()),
                         "service_dates": unique_dates,
                         "calendar_span_days": span_days,
                         "missing_calendar_days": missing_calendar_days,
                         "region_day_shares": region_day_shares,
                         "first_date": str(dates.min().date()) if unique_dates else None,
                         "last_date": str(dates.max().date()) if unique_dates else None,
                         "regions": regions, "modes": modes, "day_periods": periods,
                         "complete_weather_share": float(weather_complete)})
    errors = sum(not c["passed"] and c["severity"] == "error" for c in checks)
    warnings = sum(not c["passed"] and c["severity"] == "warning" for c in checks)
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "invalid" if errors else "development" if warnings else "coverage_targets_met",
        "errors": errors, "warnings": warnings, "coverage": coverage, "checks": checks,
        "interpretation": "Passing these checks does not establish representativeness or submission "
                          "completion. Review source coverage, collection gaps and all results.",
        "manual_requirements": ["Lecturer concept approval", "Group understanding and interpretation",
                                "Public GitHub URL", "Final PDF with evidence appendix",
                                "Recorded video: five minutes per student", "Moodle submission"],
    }


def run_quality_audit() -> dict:
    PATHS.ensure()
    path = PATHS.processed / "model_data.csv"
    if not path.exists():
        raise FileNotFoundError("Run prepare and integrate before validate.")
    result = assess_data(pd.read_csv(path, dtype={"station_id": "string"}), load_settings())
    (PATHS.tables / "quality_audit.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    pd.DataFrame(result["checks"]).to_csv(PATHS.tables / "quality_checks.csv", index=False)
    print(f"Data status: {result['status']}; errors: {result['errors']}; "
          f"coverage warnings: {result['warnings']}")
    for check in result["checks"]:
        if not check["passed"]:
            print(f"  {check['severity'].upper()}: {check['check']} - {check['detail']}")
    return result
