"""Rebuild development results from saved data; --collect fetches fresh API data."""

from __future__ import annotations

import argparse

from sptdelays.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true", help="Fetch a fresh transport snapshot and weather")
    args = parser.parse_args()
    if args.collect:
        from sptdelays.collect_live import collect_live
        from sptdelays.collect_weather import collect_weather
        from sptdelays.prepare import prepare_transport

        collect_live()
        prepare_transport("live")
        collect_weather()
    run_pipeline("live")


if __name__ == "__main__":
    main()
