"""Forecast origins and model inputs of both stages."""

import holidays
import numpy as np
import pandas as pd

from co2_forecast.ned import HOUR, SERIES

ENERGY = list(SERIES)
HORIZON_HOURS = 7 * 24
# The weekly mean and the oldest daily value reach this far back from the end of the history.
HISTORY_HOURS = 168
TRAINING_WINDOW = pd.DateOffset(months=12)
ORIGIN_STEP = "6h"
DAILY_POINTS = 7
RECENT_HOURS = 3


def origin_name(origin: pd.Timestamp) -> str:
    return f"{origin:%Y-%m-%d_%H}Z"


def target_times(origin: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(origin, periods=HORIZON_HOURS, freq="h", name="time")


def history_start(origin: pd.Timestamp) -> pd.Timestamp:
    """Start of the first-stage history, which ends one buffer hour before `origin`."""
    return origin - HOUR - HISTORY_HOURS * HOUR


def training_origins(table: pd.DataFrame, moment: pd.Timestamp, label_columns: list[str]) -> list[pd.Timestamp]:
    """Origins on the 6-hour grid within the training window whose 168 labels are all available at `moment`.

    Origins whose history or labels touch a gap in the NED history are skipped as a whole.
    """
    last = moment - HOUR - HORIZON_HOURS * HOUR
    grid = pd.date_range((moment - TRAINING_WINDOW).ceil(ORIGIN_STEP), last, freq=ORIGIN_STEP)
    return [
        t
        for t in grid
        if _known(table, history_start(t), t - HOUR, ENERGY)
        and _known(table, t, t + HORIZON_HOURS * HOUR, label_columns)
    ]


def energy_features(table: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """149 first-stage inputs for each of the 168 target hours, using history that ends one hour before `origin`."""
    values = table[ENERGY].to_numpy()
    history_end = (origin - HOUR - table.index[0]) // HOUR
    if history_end < HISTORY_HOURS:
        raise ValueError(f"History before {origin} is too short for first-stage features")

    horizon = np.arange(HORIZON_HOURS)
    # The latest interval with the target's UTC hour that ends by the history end, then whole days back.
    latest_daily = history_end + 1 + horizon - 24 * np.ceil((horizon + 2) / 24).astype(int)
    daily = values[latest_daily[:, None] - 24 * np.arange(DAILY_POINTS)]
    recent = values[history_end - np.arange(1, RECENT_HOURS + 1)]
    means = {hours: values[history_end - hours : history_end].mean(axis=0) for hours in (24, HISTORY_HOURS)}

    columns = {}
    for i, name in enumerate(ENERGY):
        for day in range(DAILY_POINTS):
            columns[f"{name}_day{day + 1}"] = daily[:, day, i]
        for lag in range(RECENT_HOURS):
            columns[f"{name}_lag{lag + 1}"] = recent[lag, i]
        for hours, mean in means.items():
            columns[f"{name}_mean{hours}"] = mean[i]
    return _with_calendar(pd.DataFrame(columns, index=target_times(origin)))


def co2_features(energy_forecast: pd.DataFrame) -> pd.DataFrame:
    """17 second-stage inputs: the 12 forecast volumes of each target hour with its calendar and horizon."""
    return _with_calendar(energy_forecast[ENERGY])


def _known(table: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, columns: list[str]) -> bool:
    """Whether every hourly value of `columns` in [start, end) is present."""
    return table.loc[start : end - HOUR, columns].notna().all(axis=None)


def _with_calendar(inputs: pd.DataFrame) -> pd.DataFrame:
    local = inputs.index.tz_convert("Europe/Amsterdam")
    nl_holidays = holidays.NL(years=set(local.year), categories=("public", "optional"))
    return inputs.assign(
        hour=local.hour,
        weekday=local.weekday,
        month=local.month,
        is_holiday=[int(day in nl_holidays) for day in local.date],
        horizon=np.arange(len(inputs)),
    )
