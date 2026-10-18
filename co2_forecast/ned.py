"""Download, store and load hourly NED Current history of the 12 energy series and the CO2 factor."""

import json
import math
import os
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://api.ned.nl"
HISTORY_DIR = Path("data/ned-history")
HOUR = pd.Timedelta(hours=1)
WEEK = pd.Timedelta(hours=168)
PAGE_SIZE = 200
# NED allows 200 requests per 5 minutes, one per 1.5 s on average; the margin absorbs timing jitter.
REQUEST_INTERVAL_SECONDS = 1.5 + 0.05
RETRY_PAUSES_SECONDS = (5, 15, 45)
TEMPORARY_HTTP_ERRORS = {429, 500, 502, 503, 504}

# Series name -> (NED type, activity). Activity 1 is Providing, 2 is Consuming.
SERIES = {
    "solar": (2, 1),
    "wind_onshore": (1, 1),
    "wind_offshore": (51, 1),
    "gas": (18, 1),
    "coal": (19, 1),
    "nuclear": (20, 1),
    "waste": (21, 1),
    "biomass": (25, 1),
    "other": (26, 1),
    "chp": (35, 1),
    "total_generation": (27, 1),
    "load": (59, 2),
}
# The CO2 target is the emission factor of ElectricityMix, stored with its volume.
CO2_SERIES = "total_generation"


def update_history(start: pd.Timestamp) -> None:
    """Bring every stored series up to the download cutoff, starting no later than `start`."""
    if not os.environ.get("NED_API_KEY"):
        raise RuntimeError("NED_API_KEY is not set; add your NED API key to .env")
    cutoff = pd.Timestamp.now(tz="UTC").floor("h") - HOUR
    for name in SERIES:
        stored = _read(name)
        downloaded = []
        for range_start, range_end in _request_ranges(stored, start, cutoff):
            print(f"Downloading {name} for [{range_start:%Y-%m-%d %H:%M}, {range_end:%Y-%m-%d %H:%M})Z")
            downloaded += _download(name, range_start, range_end)
        _validate(name, downloaded)
        merged = {record["validfrom"]: record for record in stored + downloaded}
        _write(name, [merged[key] for key in sorted(merged)])


def load_table(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Hourly volumes (kWh) of all series and the CO2 factor (gCO2/kWh) for interval starts in [start, end).

    Hours missing from the NED history are left empty.
    """
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    columns = {}
    for name in SERIES:
        series = pd.DataFrame(_read(name), columns=["validfrom", "volume", "emissionfactor"])
        series.index = pd.to_datetime(series["validfrom"], utc=True)
        columns[name] = series["volume"].reindex(hours)
        if name == CO2_SERIES:
            columns["co2"] = series["emissionfactor"].reindex(hours) * 1000
    return pd.DataFrame(columns)


def records(start: pd.Timestamp, end: pd.Timestamp) -> dict[str, list[dict]]:
    """Original NED records of every series with interval starts in [start, end)."""
    return {name: [r for r in _read(name) if start <= pd.Timestamp(r["validfrom"]) < end] for name in SERIES}


def describe_gaps(table: pd.DataFrame) -> list[str]:
    """One line per column with missing hours, naming their count and intervals."""
    report = []
    for name, column in table.items():
        missing = column.index[column.isna()]
        if len(missing):
            ranges = [f"[{a:%Y-%m-%d %H:%M}, {b:%Y-%m-%d %H:%M})Z" for a, b in _hour_ranges(missing)]
            shown = ", ".join(ranges[:5]) + (" ..." if len(ranges) > 5 else "")
            report.append(f"{name}: {len(missing)} hours missing in {shown}")
    return report


def _request_ranges(
    stored: list[dict], start: pd.Timestamp, cutoff: pd.Timestamp
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Each stretch of hours missing before the stored end, then the week before that end and everything newer."""
    if not stored:
        return [(start, cutoff)]
    overlap_start = max(start, pd.Timestamp(stored[-1]["validto"]) - WEEK)
    stored_hours = pd.DatetimeIndex(pd.to_datetime([r["validfrom"] for r in stored], utc=True))
    missing = pd.date_range(start, overlap_start, freq="h", inclusive="left").difference(stored_hours)
    return [*_hour_ranges(missing), (overlap_start, cutoff)]


def _download(name: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """All Current hourly national records with interval starts in [start, end), oldest first."""
    type_id, activity = SERIES[name]
    url = f"{API}/v1/utilizations"
    params = {
        "point": 0,
        "type": type_id,
        "activity": activity,
        "classification": 2,
        "granularity": 5,
        "granularitytimezone": 0,
        # Date filters accept whole UTC dates only; the hours outside [start, end) are dropped below.
        "validfrom[after]": f"{start:%Y-%m-%d}",
        "validfrom[strictly_before]": f"{end.ceil('D'):%Y-%m-%d}",
        "order[validfrom]": "asc",
        "itemsPerPage": PAGE_SIZE,
    }
    downloaded = []
    while url:
        requested_at = time.monotonic()
        page = _get(url, params)
        downloaded += page["hydra:member"]
        next_page = page.get("hydra:view", {}).get("hydra:next")
        url, params = (API + next_page, None) if next_page else (None, None)
        time.sleep(max(0, REQUEST_INTERVAL_SECONDS - (time.monotonic() - requested_at)))
    return [r for r in downloaded if start <= pd.Timestamp(r["validfrom"]) < end]


def _get(url: str, params: dict | None) -> dict:
    headers = {"X-AUTH-TOKEN": os.environ["NED_API_KEY"], "Accept": "application/ld+json"}
    for pause in (*RETRY_PAUSES_SECONDS, None):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=60)
            if response.status_code not in TEMPORARY_HTTP_ERRORS:
                response.raise_for_status()
                return response.json()
            error = f"HTTP {response.status_code}"
        except (requests.ConnectionError, requests.Timeout) as exception:
            error = str(exception)
        if pause is None:
            raise RuntimeError(f"NED request failed after retries: {error}")
        print(f"NED request failed ({error}), retrying in {pause} s")
        time.sleep(pause)


def _validate(name: str, downloaded: list[dict]) -> None:
    fields = ["volume", "emissionfactor"] if name == CO2_SERIES else ["volume"]
    starts = pd.to_datetime([r["validfrom"] for r in downloaded], utc=True)
    ends = pd.to_datetime([r["validto"] for r in downloaded], utc=True)
    problems = {
        "not on an hour boundary": (starts != starts.floor("h")).any(),
        "not one hour long": (ends - starts != HOUR).any(),
        "duplicate intervals": starts.duplicated().any(),
        "non-numeric or non-finite values": not all(
            isinstance(r[field], int | float) and math.isfinite(r[field]) for r in downloaded for field in fields
        ),
    }
    found = [problem for problem, present in problems.items() if present]
    if found:
        raise ValueError(f"Invalid NED download for {name}: {', '.join(found)}")


def _hour_ranges(hours: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous [start, end) intervals covering the given hours."""
    series = hours.to_series()
    groups = series.groupby((series.diff() != HOUR).cumsum())
    return [(group.iloc[0], group.iloc[-1] + HOUR) for _, group in groups]


def _read(name: str) -> list[dict]:
    path = HISTORY_DIR / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else []


def _write(name: str, history: list[dict]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{name}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(history))
    temporary.replace(path)
