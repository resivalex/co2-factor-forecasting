"""Inputs of the CO2 model: same-hour volumes of the input series, residual load and the calendar."""

import holidays
import pandas as pd

from co2_forecast.ned import INPUTS

HORIZON_HOURS = 7 * 24
TRAINING_WINDOW = pd.DateOffset(months=12)
WEATHER_DRIVEN = ["solar", "wind_onshore", "wind_offshore"]


def origin_name(origin: pd.Timestamp) -> str:
    return f"{origin:%Y-%m-%d_%H}Z"


def target_times(origin: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(origin, periods=HORIZON_HOURS, freq="h", name="time")


def features(volumes: pd.DataFrame) -> pd.DataFrame:
    """Model inputs for each hour of `volumes`.

    Residual load is the demand left after solar and wind, which dispatchable, mostly fossil, plants must cover.
    """
    inputs = volumes[INPUTS].assign(residual_load=volumes["load"] - volumes[WEATHER_DRIVEN].sum(axis=1))
    local = inputs.index.tz_convert("Europe/Amsterdam")
    nl_holidays = holidays.NL(years=set(local.year), categories=("public", "optional"))
    return inputs.assign(
        hour=local.hour,
        weekday=local.weekday,
        month=local.month,
        is_holiday=[int(day in nl_holidays) for day in local.date],
    )
