# CO₂ Factor Forecasting

Forecasts the CO₂ factor of Dutch electricity production for the next 168 hours, one value per hour,
from renewable energy production data of the [Nationaal Energie Dashboard (NED)](https://ned.nl).

## Run

Requires Docker with Compose.
Copy `.env.example` to `.env`, add your NED API key, and run

```bash
docker compose run --rm pipeline
```

The pipeline runs fetch, train, evaluate and forecast in order. Each step is a module in `co2_forecast/`.
All downloaded data and outputs go to `data/`.

## Develop

Requires [uv](https://docs.astral.sh/uv/).

- `uv run ruff format .` formats the code.
- `uv run ruff check --fix .` lints and fixes what it can.
- `uv add <package>` adds a dependency to `pyproject.toml` and pins it in `uv.lock`.
