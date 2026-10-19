"""The CO2 model: one LightGBM regressor from same-hour input volumes and the calendar to NED's CO2 factor.

It is trained on Current history, where the inputs are actual volumes, and applied to NED's Forecast of them.
"""

import lightgbm as lgb
import pandas as pd

from co2_forecast.features import features

# Selected on validation among five configurations, see docs/report.md.
PARAMS = {
    "objective": "regression",
    "learning_rate": 0.05,
    "num_iterations": 300,
    "min_data_in_leaf": 100,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 10,
    "verbosity": -1,
}


def fit(table: pd.DataFrame) -> lgb.Booster:
    """Train on every hour of `table` whose inputs and CO2 factor are all present."""
    complete = table.dropna()
    return lgb.train(PARAMS, lgb.Dataset(features(complete), complete["co2_factor"].to_numpy()))


def predict(model: lgb.Booster, volumes: pd.DataFrame) -> pd.Series:
    """CO2 factor (gCO2/kWh) for each hour of `volumes`, clipped at zero."""
    return pd.Series(model.predict(features(volumes)), index=volumes.index, name="co2_factor").clip(lower=0)
