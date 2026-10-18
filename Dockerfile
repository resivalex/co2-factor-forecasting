FROM python:3.12.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.4 /uv /bin/uv
# OpenMP runtime required by LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# The container user has no writable home for the Matplotlib cache
ENV MPLCONFIGDIR=/tmp/matplotlib

COPY co2_forecast co2_forecast

CMD ["python", "-m", "co2_forecast"]
