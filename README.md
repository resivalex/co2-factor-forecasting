# CO₂ Factor Forecasting

Forecasts the CO₂ factor of Dutch electricity production for the next 168 hours, one value per hour,
from the data of the [Nationaal Energie Dashboard (NED)](https://ned.nl).

## Setup

Requires Docker with Compose. Create `.env` and add your NED API key to it:

```bash
cp .env.example .env
```

## Usage

Forecast from the start of the current UTC hour:

```bash
docker compose run --rm pipeline
```

Forecast from a given UTC hour, here 1 October 2026, 12:00:

```bash
docker compose run --rm pipeline python -m co2_forecast --date 2026-10-01 --utc-hour 12
```

The result goes to `data/co2-forecasts/2026-10-01_12Z/`:

- `co2-forecast.csv`: 168 rows with two columns:
  - `time`: the UTC start of the hour, such as `2026-10-01T12:00:00Z`;
  - `co2_factor`: the forecast in gCO₂/kWh.
- `co2-forecast.png`: the forecast chart in UTC.
- `ned-inputs.json`: the NED records the forecast was made from.

Notes:

- An existing result is overwritten only after you confirm.
- The first run takes about 45 minutes: 30 to download two years of NED history and 15 to prepare
  historical energy forecasts. Later runs reuse both from `data/`.
- After changing the energy models, delete `data/energy-forecast-cache/` to recalculate the historical forecasts.
- Behind a proxy, add `-e HTTPS_PROXY=http://host.docker.internal:<port>` after `run`.

## Develop

Requires [uv](https://docs.astral.sh/uv/).

- `uv run ruff format .` formats the code.
- `uv run ruff check --fix .` lints and fixes what it can.
- `uv add <package>` adds a dependency and pins it in `uv.lock`.
