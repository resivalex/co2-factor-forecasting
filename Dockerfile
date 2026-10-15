FROM python:3.12.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.4 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

COPY co2_forecast co2_forecast

# Placeholder; pipeline steps are run via `docker compose run --rm pipeline`
CMD ["python", "--version"]
