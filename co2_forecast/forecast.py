"""Produce the 168-hour CO2 factor forecast from a given origin and save it under data/co2-forecasts/."""

import json
import shutil
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

from co2_forecast import ned
from co2_forecast.features import ENERGY, TRAINING_WINDOW, co2_features, history_start, origin_name
from co2_forecast.train import fit_co2, forecast_energy, retrain_moment

OUTPUT_DIR = Path("data/co2-forecasts")


def forecast(origin: pd.Timestamp) -> None:
    """Update NED history, train both stages on data available at `origin` and save its forecast."""
    directory = OUTPUT_DIR / origin_name(origin)
    if directory.exists() and input(f"{directory} exists. Recalculate and overwrite it? [y/N] ").lower() != "y":
        print("Kept the existing forecast")
        return

    # Second-stage training origins reach a year back, and their energy models train on the year before their month.
    start = history_start(retrain_moment(origin - TRAINING_WINDOW) - TRAINING_WINDOW)
    end = origin - ned.HOUR
    ned.update_history(start)
    table = ned.load_table(start, end)
    if gaps := ned.describe_gaps(table.loc[history_start(origin) :, ENERGY]):
        raise ValueError("NED history needed for the forecast inputs is incomplete:\n" + "\n".join(gaps))
    if gaps := ned.describe_gaps(table):
        print("Skipping training origins that touch NED gaps:\n" + "\n".join(gaps))

    co2_model = fit_co2(table, origin)
    print(f"Forecasting origin {origin_name(origin)}")
    energy = forecast_energy(table, origin)
    co2 = pd.DataFrame({"co2_factor": co2_model.predict(co2_features(energy))}, index=energy.index).clip(lower=0)

    _save(directory, co2, ned.records(start, end))
    try:
        _plot(co2["co2_factor"], directory / "co2-forecast.png")
    except Exception as error:  # noqa: BLE001 - a failed plot must not discard the saved forecast
        print(f"Warning: could not save the forecast plot ({error!r}); the forecast is saved in {directory}")
    print(f"Saved the forecast to {directory}")


def _save(directory: Path, co2: pd.DataFrame, inputs: dict[str, list[dict]]) -> None:
    """Write the result next to its final location, then replace any previous result as a whole."""
    temporary = directory.with_name(f".{directory.name}.tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    co2.to_csv(temporary / "co2-forecast.csv", date_format="%Y-%m-%dT%H:%M:%SZ")
    (temporary / "ned-inputs.json").write_text(json.dumps(inputs))
    shutil.rmtree(directory, ignore_errors=True)
    temporary.rename(directory)


def _plot(co2: pd.Series, path: Path) -> None:
    figure = Figure(figsize=(10, 4))
    axes = figure.subplots()
    axes.plot(co2.index, co2.to_numpy(), color="black", linewidth=1.2)
    axes.set_title("CO₂ factor forecast, gCO₂/kWh")
    axes.set_xlabel("UTC")
    axes.xaxis.set_major_locator(mdates.DayLocator(tz="UTC"))
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %b", tz="UTC"))
    axes.grid(axis="y", color="lightgray", linewidth=0.6)
    axes.spines[["top", "right"]].set_visible(False)
    axes.set_ylim(bottom=0)
    figure.savefig(path, dpi=150, bbox_inches="tight")
