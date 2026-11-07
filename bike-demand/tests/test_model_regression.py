"""Regression check: the served bundle reproduces the prediction recorded at acceptance."""

import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

from bike_demand.preflight import sha256
from bike_demand.promote import REFERENCE_INPUT

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.accepted_model
def test_recorded_model_prediction():
    """artifacts/ must hold the accepted bundle and reproduce its recorded value."""
    accepted = json.loads((PROJECT_ROOT / "registry/accepted.json").read_text())
    artifacts = PROJECT_ROOT / "artifacts"

    assert sha256(artifacts / "model.joblib") == accepted["model_sha256"]
    metadata = json.loads((artifacts / "model-metadata.json").read_text())
    assert metadata["model_version"] == accepted["model_version"]

    model = joblib.load(artifacts / "model.joblib")

    # Use the feature order recorded with the model, not dictionary order.
    feature_names = metadata["features"]
    features = pd.DataFrame(
        [[REFERENCE_INPUT[name] for name in feature_names]],
        columns=feature_names,
    )

    actual = float(model.predict(features)[0])

    assert actual == pytest.approx(
        accepted["reference_prediction"],
        abs=1e-6,
        rel=0,
    )
