"""Produce the 168-hour CO2 factor forecast from the current hour and save it under data/co2-forecasts/."""

import io
import shutil
import tarfile
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

from co2_forecast import ned
from co2_forecast.features import TRAINING_WINDOW, origin_name, target_times
from co2_forecast.model import fit, predict

OUTPUT_DIR = Path("data/co2-forecasts")
# Fixed start of the stored history, so every installation downloads the same range, see docs/data-and-approach.md.
HISTORY_START = pd.Timestamp("2025-09-01", tz="UTC")


def forecast(origin: pd.Timestamp) -> None:
    """Train the CO2 model on the year of NED history before `origin` and apply it to NED's input forecast."""
    directory = OUTPUT_DIR / origin_name(origin)
    if directory.exists() and input(f"{directory} exists. Recalculate and overwrite it? [y/N] ").lower() != "y":
        print("Kept the existing forecast")
        return

    start = origin - TRAINING_WINDOW
    end = origin - ned.HOUR
    ned.update_history(min(HISTORY_START, start))
    table = ned.load_table(start, end)
    if gaps := ned.describe_gaps(table):
        print("Training skips hours with gaps in the NED history:\n" + "\n".join(gaps))

    hours = target_times(origin)
    forecast_records = ned.download_forecast(hours[0], hours[-1] + ned.HOUR)
    # The last hour of NED's Forecast often holds only part of the hour, so it is dropped and filled like a missing one.
    volumes = ned.hourly({name: records.iloc[:-1] for name, records in forecast_records.items()}, hours)
    # If NED's Forecast ends short of the horizon, the missing hours repeat the previous day.
    volumes = volumes.fillna(volumes.shift(24))
    if gaps := ned.describe_gaps(volumes):
        raise ValueError("NED's Forecast of the model inputs is incomplete:\n" + "\n".join(gaps))

    print(f"Forecasting origin {origin_name(origin)}")
    co2 = predict(fit(table), volumes)

    inputs = {f"history/{name}.csv": records for name, records in ned.records(start, end).items()}
    inputs |= {f"forecast/{name}.csv": records for name, records in forecast_records.items()}
    _save(directory, co2, inputs)
    try:
        _plot(co2, directory / "co2-forecast.png")
    except Exception as error:  # noqa: BLE001 - a failed plot must not discard the saved forecast
        print(f"Warning: could not save the forecast plot ({error!r}). The forecast is saved in {directory}")
    print(f"Saved the forecast to {directory}")


def _save(directory: Path, co2: pd.Series, inputs: dict[str, pd.DataFrame]) -> None:
    """Write the result next to its final location, then replace any previous result as a whole."""
    temporary = directory.with_name(f".{directory.name}.tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    co2.to_csv(temporary / "co2-forecast.csv", date_format="%Y-%m-%dT%H:%M:%SZ")
    with tarfile.open(temporary / "ned-inputs.tar.gz", "w:gz") as archive:
        for path, records in inputs.items():
            data = records.to_csv(index=False).encode()
            entry = tarfile.TarInfo(path)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    shutil.rmtree(directory, ignore_errors=True)
    temporary.rename(directory)


def _plot(co2: pd.Series, path: Path) -> None:
    figure = Figure(figsize=(10, 4))
    axes = figure.subplots()
    axes.plot(co2.index, co2.to_numpy(), color="black", linewidth=1.2)
    axes.set_ylabel("CO₂ factor forecast, gCO₂/kWh")
    axes.set_xlabel("UTC")
    axes.xaxis.set_major_locator(mdates.DayLocator(tz="UTC"))
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b", tz="UTC"))
    axes.grid(axis="y", color="lightgray", linewidth=0.6)
    axes.spines[["top", "right"]].set_visible(False)
    axes.set_ylim(bottom=0)
    figure.savefig(path, dpi=150, bbox_inches="tight")
