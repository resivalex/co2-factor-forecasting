# CO₂ Factor Forecasting

Forecasts the CO₂ factor of Dutch electricity production for the next 168 hours, one value per hour, from the forecast of renewable generation and demand by the [Nationaal Energie Dashboard (NED)](https://ned.nl). A LightGBM model, retrained at each run on the last 12 months of NED history, maps these forecasts to the CO₂ factor. The approach and its evaluation are in the report, as [PDF](docs/report.pdf) or [Markdown](docs/report.md).

## Setup

Requires Docker with Compose and a NED API key from your account on [ned.nl](https://ned.nl).

1. Run `docker compose run --rm pipeline`. The first run creates `.env` from `.env.example` and stops.
2. Add your key to `.env` as `NED_API_KEY=...`.

## Usage

Forecast the 168 hours from the start of the current UTC hour:

```bash
docker compose run --rm pipeline
```

The first run starts from the NED history in `data/seed/`, which ends on 19 October 2026, and downloads only the newer hours.

The result goes to `data/co2-forecasts/<UTC date>_<UTC hour>Z/`, such as `2026-10-18_21Z/`:

- `co2-forecast.csv`: 168 rows with two columns
  - `time`: the UTC start of the hour, such as `2026-10-18T21:00:00Z`.
  - `co2_factor`: the forecast in gCO₂/kWh.
- `co2-forecast.png`: the forecast chart in UTC.

If the result for this hour exists, the run stops. To recalculate and overwrite it:

```bash
docker compose run --rm pipeline --overwrite
```

## Project structure

- `co2_forecast/`: the pipeline
  - `ned.py`: downloads and validates NED's Current history and Forecast, and stores the history.
  - `features.py`: builds model inputs from input volumes, adding residual load and the calendar.
  - `model.py`: trains the LightGBM model and predicts the CO₂ factor.
  - `forecast.py`: runs the forecast and saves its CSV and chart.
- `docs/`: the report and its images.
- `data/`:
  - `seed/`: NED history up to 19 October 2026, from which the first run starts.
  - `ned-history/` and `co2-forecasts/`: stored NED series and results, filled at run time.
- `Dockerfile`, `compose.yaml`: the container that runs the pipeline.
- `pyproject.toml`, `uv.lock`: dependencies.

## Develop

Requires [uv](https://docs.astral.sh/uv/).

- `uv run python -m co2_forecast` runs the pipeline without Docker.
- `uv run ruff format .` formats the code.
- `uv run ruff check --fix .` lints and fixes what it can.
- `uv add <package>` adds a dependency and pins it in `uv.lock`.
