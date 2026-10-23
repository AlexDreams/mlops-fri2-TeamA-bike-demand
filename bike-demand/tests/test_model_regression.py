"""Regression check for the recorded Bike Demand prediction."""

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REFERENCE_INPUT = {
    "season": 1,
    "yr": 1,
    "mnth": 1,
    "hr": 23,
    "holiday": 1,
    "weekday": 6,
    "workingday": 1,
    "weathersit": 1,
    "temp": 1.0,
    "atemp": 1.0,
    "hum": 1.0,
    "windspeed": 1.0,
}

REFERENCE_PREDICTION = 83.56200000000001
EXPECTED_MODEL_VERSION = "baseline-f01a22df4c39"


def test_recorded_model_prediction():
    """The saved model must reproduce the previously recorded prediction."""
    artifacts = PROJECT_ROOT / "artifacts"

    with (artifacts / "model-metadata.json").open(encoding="utf-8") as f:
        metadata = json.load(f)

    assert metadata["model_version"] == EXPECTED_MODEL_VERSION

    model = joblib.load(artifacts / "model.joblib")

    # Use the feature order recorded with the model, not dictionary order.
    feature_names = metadata["features"]
    features = pd.DataFrame(
        [[REFERENCE_INPUT[name] for name in feature_names]],
        columns=feature_names,
    )

    actual = float(model.predict(features)[0])

    assert actual == pytest.approx(
        REFERENCE_PREDICTION,
        abs=1e-6,
        rel=0,
    )
