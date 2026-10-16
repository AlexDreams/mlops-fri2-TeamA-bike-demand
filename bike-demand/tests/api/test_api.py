
import json
import math

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from bike_demand.api import create_app
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES


VALID_REQUEST = {
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


class FakeModel:
    def predict(self, dataframe):
        assert list(dataframe.columns) == list(FEATURES)
        return np.array([83.562])


@pytest.fixture
def model_artifacts(tmp_path):
    model_path = tmp_path / "model.joblib"
    joblib.dump(FakeModel(), model_path)

    metadata = {
        "model_version": "test-model-v1",
        "model_sha256": sha256(model_path),
        "features": list(FEATURES),
    }

    (tmp_path / "model-metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    return tmp_path


def test_health_with_model(model_artifacts):
    app = create_app(model_artifacts)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_version"] == "test-model-v1"


def test_predict_valid_request(model_artifacts):
    app = create_app(model_artifacts)

    with TestClient(app) as client:
        response = client.post("/predict", json=VALID_REQUEST)

    assert response.status_code == 200

    body = response.json()
    assert math.isfinite(body["prediction"])
    assert body["prediction"] >= 0
    assert body["prediction"] == pytest.approx(83.562)
    assert body["model_version"] == "test-model-v1"


@pytest.mark.parametrize(
    "field,invalid_value",
    [
        ("season", 9),
        ("hr", 25),
        ("hum", 1.5),
        ("weekday", -1),
        ("temp", "invalid"),
    ],
)
def test_predict_invalid_request(model_artifacts, field, invalid_value):
    app = create_app(model_artifacts)
    payload = {**VALID_REQUEST, field: invalid_value}

    with TestClient(app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 422


def test_predict_missing_field(model_artifacts):
    app = create_app(model_artifacts)
    payload = VALID_REQUEST.copy()
    del payload["season"]

    with TestClient(app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 422


def test_predict_extra_field(model_artifacts):
    app = create_app(model_artifacts)
    payload = {**VALID_REQUEST, "cnt": 100}

    with TestClient(app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 422


def test_health_without_model(tmp_path):
    app = create_app(tmp_path)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503


def test_predict_without_model(tmp_path):
    app = create_app(tmp_path)

    with TestClient(app) as client:
        response = client.post("/predict", json=VALID_REQUEST)

    assert response.status_code == 503


def test_model_checksum_mismatch(model_artifacts):
    metadata_path = model_artifacts / "model-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["model_sha256"] = "incorrect-checksum"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    app = create_app(model_artifacts)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503