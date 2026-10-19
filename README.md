# CO₂ Factor Forecasting

Forecasts the CO₂ factor of Dutch electricity production for the next 168 hours, one value per hour,
from the forecast of renewable generation and demand by the [Nationaal Energie Dashboard (NED)](https://ned.nl).
The approach and its evaluation are in the report, as [PDF](docs/report.pdf) or [Markdown](docs/report.md). The data and the run in detail are in
[data and approach](docs/data-and-approach.md).

## Setup

Requires Docker with Compose. Create `.env` and add your NED API key to it:

```bash
cp .env.example .env
```

## Usage

Forecast the 168 hours from the start of the current UTC hour:

```bash
docker compose run --rm pipeline
```

The result goes to `data/co2-forecasts/<UTC date>_<UTC hour>Z/`, such as `2026-10-18_21Z/`:

- `co2-forecast.csv`: 168 rows with two columns
  - `time`: the UTC start of the hour, such as `2026-10-18T21:00:00Z`.
  - `co2_factor`: the forecast in gCO₂/kWh.
- `co2-forecast.png`: the forecast chart in UTC.
- `ned-inputs.tar.gz`: the NED records the forecast was made from, one CSV per series,
  with the training history in `history/` and NED's input forecast in `forecast/`.

Notes:

- An existing result is overwritten only after you confirm.
- The first run takes about 10 minutes to download NED history from 1 September 2025. Later runs reuse it from `data/`
  and take under a minute.
- Behind a proxy, add `-e HTTPS_PROXY=http://host.docker.internal:<port>` after `run`.

## Project structure

- `co2_forecast/`: the pipeline, run as `python -m co2_forecast`
  - `ned.py`: downloads and validates NED's Current history and Forecast, and stores the history.
  - `features.py`: builds model inputs from input volumes and the calendar.
  - `model.py`: trains the LightGBM model and predicts the CO₂ factor.
  - `forecast.py`: runs the forecast and saves its CSV, chart and inputs.
- `docs/`: the report and its images, and the data and approach notes.
- `data/`: created at run time, with stored NED series in `ned-history/` and results in `co2-forecasts/`.
- `Dockerfile`, `compose.yaml`: the container that runs the pipeline.
- `pyproject.toml`, `uv.lock`: dependencies.

## Develop

Requires [uv](https://docs.astral.sh/uv/).

- `uv run ruff format .` formats the code.
- `uv run ruff check --fix .` lints and fixes what it can.
- `uv add <package>` adds a dependency and pins it in `uv.lock`.
