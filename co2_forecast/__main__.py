"""Forecast the CO2 factor for the 168 hours from the current UTC hour: `python -m co2_forecast`."""

import pandas as pd

from co2_forecast.forecast import forecast

if __name__ == "__main__":
    forecast(pd.Timestamp.now(tz="UTC").floor("h"))
