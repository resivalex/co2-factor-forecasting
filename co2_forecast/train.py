"""Train both LightGBM stages in memory; cache the historical energy forecasts that train the second stage."""

from itertools import groupby
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from co2_forecast.features import ENERGY, co2_features, energy_features, origin_name, training_origins

CACHE_DIR = Path("data/energy-forecast-cache")
# Default LightGBM settings until hyperparameters are selected on validation.
PARAMS = {"objective": "regression", "verbosity": -1}


def forecast_energy(table: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    """Forecast the 168 hours of every energy series with models trained on the year before `origin`."""
    return _predict_energy(_fit_energy(table, origin), table, origin)


def fit_co2(table: pd.DataFrame, moment: pd.Timestamp) -> lgb.Booster:
    """Fit the CO2 factor regressor on historical energy forecasts issued during the year before `moment`."""
    origins = training_origins(table, moment, ["co2"])
    inputs = pd.concat([co2_features(forecast) for forecast in _historical_energy_forecasts(table, origins)])
    return _fit(inputs, table.loc[inputs.index, "co2"])


def retrain_moment(origin: pd.Timestamp) -> pd.Timestamp:
    """Historical energy forecasts reuse the models trained at the start of their UTC month."""
    return origin.replace(day=1, hour=0)


def _historical_energy_forecasts(table: pd.DataFrame, origins: list[pd.Timestamp]) -> list[pd.DataFrame]:
    for moment, month_origins in groupby(origins, key=retrain_moment):
        missing = [origin for origin in month_origins if not _cache_path(origin).exists()]
        if missing:
            print(f"Forecasting energy for {len(missing)} historical origins with models of {origin_name(moment)}")
            models = _fit_energy(table, moment)
            for origin in missing:
                _write_cache(origin, _predict_energy(models, table, origin))
    return [pd.read_csv(_cache_path(origin), index_col="time", parse_dates=["time"]) for origin in origins]


def _fit_energy(table: pd.DataFrame, moment: pd.Timestamp) -> dict[str, lgb.Booster]:
    inputs = pd.concat([energy_features(table, t) for t in training_origins(table, moment, ENERGY)])
    return {name: _fit(inputs, table.loc[inputs.index, name]) for name in ENERGY}


def _predict_energy(models: dict[str, lgb.Booster], table: pd.DataFrame, origin: pd.Timestamp) -> pd.DataFrame:
    inputs = energy_features(table, origin)
    forecast = {name: model.predict(inputs) for name, model in models.items()}
    return pd.DataFrame(forecast, index=inputs.index).clip(lower=0)


def _fit(inputs: pd.DataFrame, target: pd.Series) -> lgb.Booster:
    return lgb.train(PARAMS, lgb.Dataset(inputs, target.to_numpy()))


def _cache_path(origin: pd.Timestamp) -> Path:
    return CACHE_DIR / f"{origin_name(origin)}.csv"


def _write_cache(origin: pd.Timestamp, forecast: pd.DataFrame) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = _cache_path(origin).with_suffix(".csv.tmp")
    forecast.to_csv(temporary, date_format="%Y-%m-%dT%H:%M:%SZ")
    temporary.replace(_cache_path(origin))
