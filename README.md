# mlops-fri2-TeamA-bike-demand

# Bike Demand Prediction (MLOps)

This repository contains the source code for the MLOps learning project (Week 1, Lab 2) focused on predicting bike demand (using the `hour.csv` dataset). The project implements a complete pipeline including strict data validation, chronological partitioning, model training (Random Forest vs. Naive Baseline), and experiment tracking with MLflow.

## Prerequisites

To run this project, you need the following:

* **Python**: Version `3.12` strictly.
* **Package Manager**: [uv](https://github.com/astral-sh/uv) for fast and deterministic dependency resolution.

## Installation

1. Clone this repository.
2. Ensure you are using Python 3.12.
3. Install dependencies and create the virtual environment from the lock file:

   ```bash
   uv sync --locked
   ```

## Project Structure

The minimal architecture expected by the preflight verification pipeline is as follows:

```text
├── configs/
│   └── baseline.yaml       # Training configuration (features, hyperparameters)
├── data/
│   ├── manifest.json       # Checksums and sizes to guarantee data integrity
│   └── raw/
│       └── hour.csv        # Frozen raw dataset (snapshot)
├── bike_demand/            # Python source code
│   ├── __init__.py
│   ├── preflight.py        # Environment and snapshot verification scripts
│   ├── split.py            # Data partitioning (Train/Val/Test)
│   ├── team.py             # Team naming utilities
│   ├── tracking.py         # MLflow recording and local storage
│   ├── train.py            # Training and evaluation pipeline
│   └── validate.py         # Strict data schema validation
├── .github/workflows/
│   └── ci.yml              # Continuous integration
├── uv.lock                 # Dependency lock file
└── pyproject.toml          # Package and dependency declarations
```

*(Note: The `artifacts/`, `reports/`, and `tracking/` directories will be generated automatically during execution).*

## Work to be Done (Expected Failures)

Several critical functions currently raise a `NotImplementedError`. This is the core task of Lab 2. You must complete the code in the following files:

1. **`validate.py`**: Complete `check_domains()` to validate value domains, finite ranges, and date windows.
2. **`split.py`**: Implement `split_data()` to assign sorted, non-empty, disjoint, and complete partitions chronologically.
3. **`train.py`**:
   * `select_features()`: Correctly filter the predictors (excluding labels and identities).
   * `compare_mean()`: Fit the comparator on training targets to create a naive baseline.
   * `fit_evaluate()`: Fit the Random Forest model on the train set and evaluate it strictly on validation rows.

## Execution Commands

### 1. Environment Verification (Preflight)

Before starting, verify that your environment, dependencies, and data integrity are correct:

```bash
python -m bike_demand.preflight
```

### 2. Data Validation

To test only your schema validation rules on the input CSV file:

```bash
python -m bike_demand.validate --data data/raw/hour.csv
```

### 3. Training

Once the TODOs are completed, run the full training pipeline using the provided configuration file:

```bash
python -m bike_demand.train --config configs/baseline.yaml
```

The models will be saved in `artifacts/`, the metrics in `reports/`, and the MLflow logs in `tracking/mlflow.db`.


## Lab 3 - Docker Build and Rerun

Lab 3 reproduces the Lab 2 baseline in a clean Docker environment using Python 3.12 and the committed `uv.lock` file. Docker Desktop (or Docker Engine) must be installed and running.

### 1. Clone the repository

```bash
git clone https://github.com/reinoD15/mlops-fri2-TeamA-bike-demand.git
cd mlops-fri2-TeamA-bike-demand/bike-demand
```

Run the following commands from the `bike-demand` directory containing the `Dockerfile`, `.dockerignore`, `pyproject.toml`, and `uv.lock`.

### 2. Build the Docker image

```bash
docker build -t bike-demand:lab3 .
```

The Dockerfile installs dependencies using `uv sync --locked`. For a build without reusing cached Docker layers, use:

```bash
docker build --no-cache -t bike-demand:lab3 .
```

### 3. Rerun the Lab 2 baseline

```bash
docker run --rm bike-demand:lab3
```

The container runs the baseline training pipeline using the frozen `data/raw/hour.csv` dataset and `configs/baseline.yaml`. It uses the same chronological split as Lab 2 and does not evaluate on the held-out test partition.

Expected validation results:

| Model | Validation MAE |
| --- | ---: |
| Naive train-mean baseline | 154.23179306864967 |
| Random Forest | 86.84685685591091 |

The expected split contains 8,645 training rows, 4,358 validation rows, and 4,376 held-out test rows. The raw data SHA-256 is `e03de4ee4ef4dc376ac6e04bf829673c6269e8eba5c60fa121640fa2f829504f`.

MLflow run IDs can differ across executions. Compare the data hash, split, configuration, validation MAEs, and saved-model readback checks instead.

### 4. Record reproducibility information

```bash
git rev-parse HEAD
docker image inspect bike-demand:lab3 --format '{{.Id}}'
```

Keep the build and run logs together with the Git commit and Docker image ID for the Lab 3 team report. The report should link the raw logs and the commit used for the rerun.

### 5. Optional local lockfile verification

If uv is installed on the host:

```bash
uv lock --check
uv sync --locked
```

A missing or outdated lockfile must be treated as an error rather than silently regenerated during the locked checks.

## Lab 4 - FastAPI model serving

Lab 4 serves the already-trained model through FastAPI. The application loads the saved model and metadata on startup; it **does not retrain** the model to handle requests.

### Endpoints

| Method | Path | Expected behavior |
| --- | --- | --- |
| `GET` | `/health` | `200` with model status and version; `503` if model unavailable |
| `POST` | `/predict` | `200` with a finite, nonnegative `prediction` and metadata-derived `model_version` |
| `POST` | `/predict` | `422` for invalid request data; `503` if model unavailable |

Interactive API documentation is available at `/docs` while the server is running.

### Prediction schema

Exactly 12 fields are required; missing or extra fields are rejected. Pydantic uses strict numeric types and checks the allowed domains.

| Feature | Type | Allowed values |
| --- | --- | --- |
| `season` | Integer | 1–4 |
| `yr` | Integer | 0–1 |
| `mnth` | Integer | 1–12 |
| `hr` | Integer | 0–23 |
| `holiday` | Integer | 0–1 |
| `weekday` | Integer | 0–6 |
| `workingday` | Integer | 0–1 |
| `weathersit` | Integer | 1–4 |
| `temp` | Float | Finite, 0–1 |
| `atemp` | Float | Finite, 0–1 |
| `hum` | Float | Finite, 0–1 |
| `windspeed` | Float | Finite, 0–1 |

### Start the API locally

Ensure `artifacts/model.joblib` and `artifacts/model-metadata.json` exist and match.

```bash
uv sync --locked
uv run --locked uvicorn bike_demand.api:app --host 127.0.0.1 --port 8000
```

Test health from a second terminal:

```bash
curl http://localhost:8000/health
```

Example prediction:

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
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
    "windspeed": 1.0
  }'
```

The response contains `prediction` and `model_version`. The numerical prediction depends on the saved model.

### Run the API in Docker

The Lab 4 Dockerfile copies the model artifacts and starts Uvicorn rather than training a model.

```bash
docker build -t bike-demand:lab4 .
docker run --rm --name bike-api -p 8000:8000 bike-demand:lab4
```

In another terminal:

```bash
curl http://localhost:8000/health
```

To stop the API:

```bash
docker stop bike-api
```

### Verification and model integrity

```bash
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q
docker run --rm bike-demand:lab4 uv run --locked pytest -q
```

The team recorded **78 passing tests** inside Docker (with one non-blocking MLflow/SQLAlchemy deprecation warning). This test result was recorded before the final Docker-serving PR; rerun tests on the merged `main` revision for final release evidence.

At startup, the API verifies that both artifact files exist, the model SHA256 matches its metadata and the feature order matches the expected schema. If these checks fail, the model is unavailable and the API responds with `503`.

To collect reproducibility identifiers:

```bash
docker image inspect bike-demand:lab4 --format '{{.Id}}'
uv run --locked python -c "from pathlib import Path; from bike_demand.preflight import sha256; print(sha256(Path('artifacts/model.joblib')))"
```

Record the image ID, model hash, model version, test output and actual HTTP responses in the Week 2 team report. The milestone tag `m2` should be created only after the final merged revision and reports have been verified.
