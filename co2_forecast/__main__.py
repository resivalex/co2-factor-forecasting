"""Forecast the CO2 factor: `python -m co2_forecast [--date YYYY-MM-DD --utc-hour H]`."""

import argparse
from datetime import date

import pandas as pd

from co2_forecast.forecast import forecast


def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast the Dutch CO2 factor for the next 168 hours.")
    parser.add_argument("--date", type=date.fromisoformat, help="UTC date of a historical origin, YYYY-MM-DD")
    parser.add_argument("--utc-hour", type=int, choices=range(24), metavar="H", help="UTC hour of that origin, 0-23")
    args = parser.parse_args()

    if args.date is None and args.utc_hour is None:
        origin = pd.Timestamp.now(tz="UTC").floor("h")
    elif args.date is None or args.utc_hour is None:
        missing = "--date" if args.date is None else "--utc-hour"
        parser.error(f"{missing} is required when the other origin argument is given")
    else:
        origin = pd.Timestamp(args.date, tz="UTC") + pd.Timedelta(hours=args.utc_hour)
    forecast(origin)


if __name__ == "__main__":
    main()
