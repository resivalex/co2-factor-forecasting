"""Forecast the CO2 factor for the 168 hours from the current UTC hour: `python -m co2_forecast [--overwrite]`."""

import argparse
import os
import shutil
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from co2_forecast.forecast import forecast

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m co2_forecast",
        description="Forecast the CO2 factor for the 168 hours from the current UTC hour.",
    )
    parser.add_argument("--overwrite", action="store_true", help="recalculate and overwrite an existing result")
    arguments = parser.parse_args()
    env = Path(".env")
    if not env.exists():
        shutil.copy(".env.example", env)
        print("Created .env from .env.example")
    load_dotenv(env)
    if not os.environ.get("NED_API_KEY"):
        sys.exit("NED_API_KEY is not set. Add your NED API key to .env")
    forecast(pd.Timestamp.now(tz="UTC").floor("h"), overwrite=arguments.overwrite)
