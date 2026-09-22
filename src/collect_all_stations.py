#!/usr/bin/env python3
"""
Collect one OJP snapshot for the selected Swiss public-transport hubs.

Each run:
- queries 16 selected stops (8 rail + 8 local public transport)
- stores the raw XML response for every successful station request
- parses the responses into one combined pandas DataFrame
- writes one combined CSV snapshot to data/interim/ojp_snapshots/

The token is never hard-coded. For manual runs, enter it when prompted.
For unattended runs, set the environment variable OJP_API_TOKEN.
"""

import os
import sys
import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape


URL = "https://api.opentransportdata.swiss/ojp20"
NUMBER_OF_RESULTS = 30
REQUEST_TIMEOUT_SECONDS = 30
PAUSE_BETWEEN_REQUESTS_SECONDS = 0.25

RAW_DIR = Path("data/raw/ojp")
SNAPSHOT_DIR = Path("data/interim/ojp_snapshots")


RAIL_STATIONS = [
    {"city": "Zürich",     "station_type": "rail",  "stop_id": "ch:1:sloid:3000",  "stop_name": "Zürich HB"},
    {"city": "Bern",       "station_type": "rail",  "stop_id": "ch:1:sloid:7000",  "stop_name": "Bern"},
    {"city": "Basel",      "station_type": "rail",  "stop_id": "ch:1:sloid:10",    "stop_name": "Basel SBB"},
    {"city": "Luzern",     "station_type": "rail",  "stop_id": "ch:1:sloid:5000",  "stop_name": "Luzern"},
    {"city": "St. Gallen", "station_type": "rail",  "stop_id": "ch:1:sloid:6302",  "stop_name": "St. Gallen"},
    {"city": "Lausanne",   "station_type": "rail",  "stop_id": "ch:1:sloid:1120",  "stop_name": "Lausanne"},
    {"city": "Genève",     "station_type": "rail",  "stop_id": "ch:1:sloid:1008",  "stop_name": "Genève"},
    {"city": "Lugano",     "station_type": "rail",  "stop_id": "ch:1:sloid:5300",  "stop_name": "Lugano"},
]

LOCAL_STATIONS = [
    {"city": "Zürich",     "station_type": "local", "stop_id": "ch:1:sloid:87348", "stop_name": "Zürich, Bahnhofplatz/HB"},
    {"city": "Bern",       "station_type": "local", "stop_id": "ch:1:sloid:76646", "stop_name": "Bern, Bahnhof"},
    {"city": "Basel",      "station_type": "local", "stop_id": "ch:1:sloid:78143", "stop_name": "Basel, Bahnhof SBB"},
    {"city": "Luzern",     "station_type": "local", "stop_id": "ch:1:sloid:8450",  "stop_name": "Luzern, Bahnhof"},
    {"city": "St. Gallen", "station_type": "local", "stop_id": "ch:1:sloid:74095", "stop_name": "St. Gallen, Bahnhof"},
    {"city": "Lausanne",   "station_type": "local", "stop_id": "ch:1:sloid:92050", "stop_name": "Lausanne, gare"},
    {"city": "Genève",     "station_type": "local", "stop_id": "ch:1:sloid:87057", "stop_name": "Genève, gare Cornavin"},
    {"city": "Lugano",     "station_type": "local", "stop_id": "ch:1:sloid:5380",  "stop_name": "Lugano, Stazione"},
]

ALL_STATIONS = RAIL_STATIONS + LOCAL_STATIONS


def get_token():
    token = os.getenv("OJP_API_TOKEN", "").strip()

    if not token:
        token = getpass("OJP API Token: ").strip()

    if not token:
        raise ValueError("Der OJP API Token ist leer.")

    return token


def safe_filename(value):
    return (
        value
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace(",", "")
        .replace("ü", "ue")
        .replace("ö", "oe")
        .replace("ä", "ae")
        .replace("é", "e")
        .replace("è", "e")
        .replace("à", "a")
    )


def parse_bool(value):
    if value is None:
        return pd.NA

    value = str(value).strip().lower()

    if value == "true":
        return True

    if value == "false":
        return False

    return pd.NA


def build_request(stop_id, stop_name, timestamp, message_id, number_of_results):
    stop_name_xml = escape(stop_name)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OJP
    xmlns="http://www.vdv.de/ojp"
    xmlns:siri="http://www.siri.org.uk/siri"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xsi:schemaLocation="http://www.vdv.de/ojp"
    version="2.0">

    <OJPRequest>
        <siri:ServiceRequest>

            <siri:ServiceRequestContext>
                <siri:Language>de</siri:Language>
            </siri:ServiceRequestContext>

            <siri:RequestTimestamp>{timestamp}</siri:RequestTimestamp>
            <siri:RequestorRef>ZHAW_DataAnalytics_Project</siri:RequestorRef>

            <OJPStopEventRequest>

                <siri:RequestTimestamp>{timestamp}</siri:RequestTimestamp>
                <siri:MessageIdentifier>{message_id}</siri:MessageIdentifier>

                <Location>
                    <PlaceRef>
                        <siri:StopPointRef>{stop_id}</siri:StopPointRef>
                        <Name>
                            <Text>{stop_name_xml}</Text>
                        </Name>
                    </PlaceRef>

                    <DepArrTime>{timestamp}</DepArrTime>
                </Location>

                <Params>
                    <NumberOfResults>{number_of_results}</NumberOfResults>
                    <StopEventType>departure</StopEventType>
                    <IncludePreviousCalls>false</IncludePreviousCalls>
                    <IncludeOnwardCalls>false</IncludeOnwardCalls>
                    <UseRealtimeData>full</UseRealtimeData>
                </Params>

            </OJPStopEventRequest>

        </siri:ServiceRequest>
    </OJPRequest>

</OJP>
"""


def parse_stop_events(xml_content, station, collection_timestamp, batch_id):
    root = ET.fromstring(xml_content)

    ns = {
        "ojp": "http://www.vdv.de/ojp",
        "siri": "http://www.siri.org.uk/siri",
    }

    results = root.findall(".//ojp:StopEventResult", ns)
    rows = []

    for result in results:
        stop_event = result.find("ojp:StopEvent", ns)

        if stop_event is None:
            continue

        this_call = stop_event.find("ojp:ThisCall/ojp:CallAtStop", ns)
        service = stop_event.find("ojp:Service", ns)

        if this_call is None or service is None:
            continue

        cancelled_text = service.findtext(
            "ojp:Cancelled",
            default=None,
            namespaces=ns,
        )

        rows.append({
            "batch_id": batch_id,
            "collection_timestamp": collection_timestamp,
            "city": station["city"],
            "station_type": station["station_type"],
            "station_id": station["stop_id"],
            "station_name": station["stop_name"],
            "stop_point_ref": this_call.findtext(
                "siri:StopPointRef",
                default=None,
                namespaces=ns,
            ),
            "operating_day": service.findtext(
                "ojp:OperatingDayRef",
                default=None,
                namespaces=ns,
            ),
            "journey_ref": service.findtext(
                "ojp:JourneyRef",
                default=None,
                namespaces=ns,
            ),
            "transport_mode": service.findtext(
                "ojp:Mode/ojp:PtMode",
                default=None,
                namespaces=ns,
            ),
            "product_category": service.findtext(
                "ojp:ProductCategory/ojp:Name/ojp:Text",
                default=None,
                namespaces=ns,
            ),
            "public_code": service.findtext(
                "ojp:PublicCode",
                default=None,
                namespaces=ns,
            ),
            "line": service.findtext(
                "ojp:PublishedServiceName/ojp:Text",
                default=None,
                namespaces=ns,
            ),
            "train_number": service.findtext(
                "ojp:TrainNumber",
                default=None,
                namespaces=ns,
            ),
            "origin": service.findtext(
                "ojp:OriginText/ojp:Text",
                default=None,
                namespaces=ns,
            ),
            "destination": service.findtext(
                "ojp:DestinationText/ojp:Text",
                default=None,
                namespaces=ns,
            ),
            "planned_platform": this_call.findtext(
                "ojp:PlannedQuay/ojp:Text",
                default=None,
                namespaces=ns,
            ),
            "estimated_platform": this_call.findtext(
                "ojp:EstimatedQuay/ojp:Text",
                default=None,
                namespaces=ns,
            ),
            "scheduled_departure": this_call.findtext(
                "ojp:ServiceDeparture/ojp:TimetabledTime",
                default=None,
                namespaces=ns,
            ),
            "estimated_departure": this_call.findtext(
                "ojp:ServiceDeparture/ojp:EstimatedTime",
                default=None,
                namespaces=ns,
            ),
            "cancelled": parse_bool(cancelled_text),
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    for column in [
        "collection_timestamp",
        "scheduled_departure",
        "estimated_departure",
    ]:
        df[column] = pd.to_datetime(
            df[column],
            utc=True,
            errors="coerce",
        )

    df["cancelled"] = df["cancelled"].astype("boolean")

    df["has_realtime"] = df["estimated_departure"].notna()

    # Important:
    # Missing EstimatedTime stays NaN and is NOT interpreted as zero delay.
    df["predicted_delay_minutes"] = (
        df["estimated_departure"]
        - df["scheduled_departure"]
    ).dt.total_seconds() / 60

    df["collection_timestamp_local"] = (
        df["collection_timestamp"].dt.tz_convert("Europe/Zurich")
    )
    df["scheduled_departure_local"] = (
        df["scheduled_departure"].dt.tz_convert("Europe/Zurich")
    )
    df["estimated_departure_local"] = (
        df["estimated_departure"].dt.tz_convert("Europe/Zurich")
    )

    df["date"] = df["scheduled_departure_local"].dt.date
    df["hour"] = df["scheduled_departure_local"].dt.hour
    df["weekday"] = df["scheduled_departure_local"].dt.day_name()
    df["weekend"] = df["scheduled_departure_local"].dt.dayofweek >= 5

    df["minutes_until_departure"] = (
        df["scheduled_departure"]
        - df["collection_timestamp"]
    ).dt.total_seconds() / 60

    return df


def collect_station(session, station, token, batch_id):
    now_utc = datetime.now(timezone.utc)
    timestamp = (
        now_utc
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    message_id = f"zhaw-collection-{uuid4()}"

    xml_request = build_request(
        stop_id=station["stop_id"],
        stop_name=station["stop_name"],
        timestamp=timestamp,
        message_id=message_id,
        number_of_results=NUMBER_OF_RESULTS,
    )

    headers = {
        "Content-Type": "application/xml",
        "Authorization": f"Bearer {token}",
    }

    response = session.post(
        URL,
        headers=headers,
        data=xml_request.encode("utf-8"),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        error_preview = response.text[:500].replace("\n", " ")
        raise RuntimeError(
            f"HTTP {response.status_code}: {error_preview}"
        )

    station_raw_dir = RAW_DIR / batch_id
    station_raw_dir.mkdir(parents=True, exist_ok=True)

    raw_filename = (
        station_raw_dir
        / f"{safe_filename(station['city'])}_"
          f"{station['station_type']}_"
          f"{safe_filename(station['stop_name'])}.xml"
    )
    raw_filename.write_bytes(response.content)

    df = parse_stop_events(
        xml_content=response.content,
        station=station,
        collection_timestamp=timestamp,
        batch_id=batch_id,
    )

    return df


def main():
    token = get_token()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    batch_time = datetime.now(timezone.utc)
    batch_id = batch_time.strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print("OJP MULTI-STATION COLLECTION")
    print("=" * 70)
    print(f"Batch: {batch_id}")
    print(f"Stations configured: {len(ALL_STATIONS)}")
    print()

    all_results = []
    failures = []

    with requests.Session() as session:
        for index, station in enumerate(ALL_STATIONS, start=1):
            label = (
                f"[{index:02d}/{len(ALL_STATIONS)}] "
                f"{station['city']} | "
                f"{station['station_type']} | "
                f"{station['stop_name']}"
            )
            print(label)

            try:
                df_station = collect_station(
                    session=session,
                    station=station,
                    token=token,
                    batch_id=batch_id,
                )

                print(f"  OK: {len(df_station)} observations")

                if not df_station.empty:
                    all_results.append(df_station)

            except Exception as exc:
                failures.append({
                    "city": station["city"],
                    "station_type": station["station_type"],
                    "stop_name": station["stop_name"],
                    "error": str(exc),
                })
                print(f"  ERROR: {exc}")

            if index < len(ALL_STATIONS):
                time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)

    print()
    print("=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)

    if not all_results:
        print("No observations were collected.")
        print(f"Failed stations: {len(failures)}")
        return 1

    df_all = pd.concat(
        all_results,
        ignore_index=True,
    )

    snapshot_filename = (
        SNAPSHOT_DIR
        / f"ojp_snapshot_{batch_id}.csv"
    )

    df_all.to_csv(
        snapshot_filename,
        index=False,
    )

    successful_stations = (
        df_all[
            ["city", "station_type", "station_id", "station_name"]
        ]
        .drop_duplicates()
        .shape[0]
    )

    print(f"Total observations: {len(df_all)}")
    print(f"Successful stations: {successful_stations}/{len(ALL_STATIONS)}")
    print(f"Failed stations: {len(failures)}")
    print(f"Combined snapshot: {snapshot_filename}")

    print("\nTransport modes:")
    print(
        df_all["transport_mode"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nObservations per city:")
    print(
        df_all["city"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(
                f"- {failure['city']} | "
                f"{failure['station_type']} | "
                f"{failure['stop_name']}: "
                f"{failure['error']}"
            )

    # Partial success is still saved.
    # Return non-zero only when every configured station failed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
