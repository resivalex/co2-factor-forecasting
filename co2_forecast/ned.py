"""Download, store and load hourly NED data: Current inputs and CO2 factor, and Forecast inputs."""

import math
import os
import time
from pathlib import Path

import pandas as pd
import requests

API = "https://api.ned.nl"
HISTORY_DIR = Path("data/ned-history")
# History shipped with the repository. A series missing from HISTORY_DIR starts from it instead of a full download.
SEED_DIR = Path("data/seed/ned-history")
HOUR = pd.Timedelta(hours=1)
WEEK = pd.Timedelta(hours=168)
PAGE_SIZE = 200
# NED allows 200 requests per 5 minutes, one per 1.5 s on average. The margin absorbs timing jitter.
REQUEST_INTERVAL_SECONDS = 1.5 + 0.05
RETRY_PAUSES_SECONDS = (5, 15, 45)
TEMPORARY_HTTP_ERRORS = {429, 500, 502, 503, 504}

CURRENT = 2
FORECAST = 1

# Series name -> (NED type, activity). Activity 1 is Providing, 2 is Consuming.
SERIES = {
    "solar": (2, 1),
    "wind_onshore": (1, 1),
    "wind_offshore": (51, 1),
    "nuclear": (20, 1),
    "biomass": (25, 1),
    "load": (59, 2),
    "total_generation": (27, 1),
}
# Model inputs. total_generation is stored only for its emissionfactor, the CO2 factor being forecast.
INPUTS = [name for name in SERIES if name != "total_generation"]
# Fields kept from each hourly NED record. The others are fixed by the request or unused.
STORED_FIELDS = ["validfrom", "volume", "emissionfactor", "lastupdate"]
# Width of the series name column in printed reports, so their dates line up.
NAME_WIDTH = max(map(len, SERIES))


def update_history(start: pd.Timestamp) -> None:
    """Bring every stored series up to the download cutoff, starting no later than `start`."""
    cutoff = pd.Timestamp.now(tz="UTC").floor("h") - HOUR
    print(f"Downloading NED history up to {cutoff:%Y-%m-%d %H:%M} UTC")
    for name in SERIES:
        history = _read(name)
        download_start = _download_start(pd.to_datetime(history["validfrom"], utc=True), start)
        print(f"  {name:<{NAME_WIDTH}}  from {download_start:%Y-%m-%d %H:%M} UTC")
        downloaded = _download(name, download_start, cutoff)
        _validate(name, downloaded)
        merged = pd.concat([history, pd.DataFrame(downloaded, columns=STORED_FIELDS)])
        _write(name, merged.drop_duplicates("validfrom", keep="last").sort_values("validfrom"))


def load_table(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Hourly input volumes (kWh) and the CO2 factor (gCO2/kWh) for interval starts in [start, end).

    Hours missing from the NED history are left empty.
    """
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    table = hourly(dict(zip(INPUTS, map(_read, INPUTS))), hours)
    total = _read("total_generation").set_index("validfrom")
    total.index = pd.to_datetime(total.index, utc=True)
    return table.assign(co2_factor=1000 * total["emissionfactor"].reindex(hours))


def download_forecast(start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """The latest records of NED's Forecast for every input series with interval starts in [start, end)."""
    print("Downloading NED forecast")
    forecast = {}
    for name in INPUTS:
        print(f"  {name}")
        downloaded = _download(name, start, end, FORECAST)
        _validate(name, downloaded)
        forecast[name] = pd.DataFrame(downloaded, columns=STORED_FIELDS)
    return forecast


def hourly(records: dict[str, pd.DataFrame], hours: pd.DatetimeIndex) -> pd.DataFrame:
    """Volumes of the given records on the given hours, empty where a record is missing."""
    columns = {}
    for name, series in records.items():
        series = series.set_index("validfrom")
        series.index = pd.to_datetime(series.index, utc=True)
        columns[name] = series["volume"].reindex(hours)
    return pd.DataFrame(columns, index=hours)


def describe_gaps(table: pd.DataFrame) -> list[str]:
    """One line per column with missing hours, naming their count and intervals."""
    report = []
    for name, column in table.items():
        missing = column.index[column.isna()]
        if len(missing):
            ranges = [f"{a:%Y-%m-%d %H:%M} to {b:%Y-%m-%d %H:%M}" for a, b in _hour_ranges(missing)]
            shown = ", ".join(ranges[:5]) + (" ..." if len(ranges) > 5 else "")
            report.append(f"  {name:<{NAME_WIDTH}}  {shown} UTC, {len(missing)} hours")
    return report


def _download_start(stored_hours: pd.Series, start: pd.Timestamp) -> pd.Timestamp:
    """Where to start downloading: the last stored week, which NED revises, or `start` if the history begins later.

    Gaps inside the stored history are NED's own and are not requested again.
    """
    if stored_hours.empty or start < stored_hours.min():
        return start
    return max(start, stored_hours.max() + HOUR - WEEK)


def _download(name: str, start: pd.Timestamp, end: pd.Timestamp, classification: int = CURRENT) -> list[dict]:
    """All hourly national records with interval starts in [start, end), oldest first."""
    type_id, activity = SERIES[name]
    url = f"{API}/v1/utilizations"
    params = {
        "point": 0,
        "type": type_id,
        "activity": activity,
        "classification": classification,
        "granularity": 5,
        "granularitytimezone": 0,
        # Date filters accept whole UTC dates only, so the hours outside [start, end) are dropped below.
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
    starts = pd.to_datetime([r["validfrom"] for r in downloaded], utc=True)
    ends = pd.to_datetime([r["validto"] for r in downloaded], utc=True)
    problems = {
        "not on an hour boundary": (starts != starts.floor("h")).any(),
        "not one hour long": (ends - starts != HOUR).any(),
        "duplicate intervals": starts.duplicated().any(),
        "non-numeric or non-finite values": not all(
            isinstance(r[field], int | float) and math.isfinite(r[field])
            for r in downloaded
            for field in ("volume", "emissionfactor")
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


def _read(name: str) -> pd.DataFrame:
    path = HISTORY_DIR / f"{name}.csv"
    if not path.exists():
        path = SEED_DIR / f"{name}.csv.gz"
    if not path.exists():
        return pd.DataFrame(columns=STORED_FIELDS)
    # The default parser may change the last bit of a float, so rewriting the history would alter NED values.
    return pd.read_csv(path, float_precision="round_trip")


def _write(name: str, history: pd.DataFrame) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = HISTORY_DIR / f"{name}.csv"
    temporary = path.with_suffix(".csv.tmp")
    history.to_csv(temporary, index=False)
    temporary.replace(path)
