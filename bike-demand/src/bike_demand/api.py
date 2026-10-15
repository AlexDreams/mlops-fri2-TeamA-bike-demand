"""Serve the trained baseline model. This module never trains."""

import json
import math
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException

from bike_demand.api_schema import PredictionRequest
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

ARTIFACTS = Path(os.environ.get("BIKE_DEMAND_ARTIFACTS", "artifacts"))


def load_model(artifacts: Path) -> dict | None:
    """Return the trusted local model and its metadata, or None if unusable."""
    model_path = artifacts / "model.joblib"
    metadata_path = artifacts / "model-metadata.json"
    if not (model_path.is_file() and metadata_path.is_file()):
        return None
    metadata = json.loads(metadata_path.read_text())
    if sha256(model_path) != metadata.get("model_sha256"):
        return None
    if metadata.get("features") != list(FEATURES):
        return None
    # Only load the locally produced model, never an uploaded file.
    return {"model": joblib.load(model_path), "metadata": metadata}


def create_app(artifacts: Path = ARTIFACTS) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.loaded = load_model(artifacts)
        yield

    app = FastAPI(title="bike-demand", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        loaded = app.state.loaded
        if loaded is None:
            raise HTTPException(status_code=503, detail="model unavailable")
        return {"status": "ok", "model_version": loaded["metadata"]["model_version"]}

    @app.post("/predict")
    def predict(request: PredictionRequest) -> dict:
        loaded = app.state.loaded
        if loaded is None:
            raise HTTPException(status_code=503, detail="model unavailable")
        row = pd.DataFrame([request.model_dump()], columns=list(FEATURES))
        value = float(loaded["model"].predict(row)[0])
        if not math.isfinite(value):
            raise HTTPException(status_code=500, detail="non-finite prediction")
        return {
            "prediction": max(0.0, value),
            "model_version": loaded["metadata"]["model_version"],
        }

    return app


app = create_app()
