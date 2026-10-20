"""Produce the 168-hour CO2 factor forecast from an origin hour and save it under data/co2-forecasts/."""

import shutil
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

from co2_forecast import ned
from co2_forecast.features import TRAINING_WINDOW, origin_name, target_times
from co2_forecast.model import fit, predict

OUTPUT_DIR = Path("data/co2-forecasts")


def forecast(origin: pd.Timestamp, overwrite: bool = False) -> None:
    """Train the CO2 model on the year of NED history before `origin` and apply it to NED's input forecast.

    An existing result for `origin` is recalculated and overwritten only with `overwrite`.
    """
    directory = OUTPUT_DIR / origin_name(origin)
    if directory.exists() and not overwrite:
        print(f"{directory} exists. To recalculate and overwrite it, run again with --overwrite")
        return

    start = origin - TRAINING_WINDOW
    end = origin - ned.HOUR
    ned.update_history(start)
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

    print(f"Forecasting {len(hours)} hours from {origin:%Y-%m-%d %H:%M} UTC")
    co2 = predict(fit(table), volumes)

    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    co2.to_csv(directory / "co2-forecast.csv", date_format="%Y-%m-%dT%H:%M:%SZ")
    try:
        _plot(co2, directory / "co2-forecast.png")
    except Exception as error:  # noqa: BLE001 - a failed plot must not discard the saved forecast
        print(f"Warning: could not save the forecast chart ({error!r})")
    print(f"Saved the forecast to {directory}")


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
