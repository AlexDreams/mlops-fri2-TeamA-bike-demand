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
Historical note: This section describes the original Lab 2 starter tasks. The implementations were completed during the earlier labs and are no longer pending work.
The following functions were originally provided as incomplete starter tasks for Lab 2 and have since been implemented:

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
git clone https://github.com/AlexDreams/mlops-fri2-TeamA-bike-demand.git
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


## Deploy

### Runtime configuration

The service runs with Uvicorn on port 8000.

Environment variables:
- `BIKE_DEMAND_ARTIFACTS`: model artifact directory (default: `artifacts`).
- `BIKE_DEMAND_REVISION`: Git revision of the deployed API code.

### Build

From the bike-demand directory, after committing the source:

```powershell
$REVISION = git rev-parse HEAD
docker build --build-arg BIKE_DEMAND_REVISION=$REVISION -t bike-demand:lab5 .
```

### Run

```powershell
docker run --rm --name bike-demand-lab5 -p 127.0.0.1:8000:8000 bike-demand:lab5
```

### Readiness

`GET /health` returns HTTP 200 only when the model has been loaded successfully.

If the model is missing or invalid, `/health` returns HTTP 503.

### Logs

The service emits structured application logs for requests.
Do not log secrets, raw prediction payloads or personal data.

### Verification

Run `scripts/verify_deployment.py` from the host against the running container.

Compare the observed model version and code revision with the values recorded for the deployment.

## Questions about deployment

### Settings: What changes between laptop and container?

The service can run locally or inside Docker. The BIKE_DEMAND_ARTIFACTS environment variable controls where the model artifacts are loaded from. If it is not set, the service uses the local artifacts/ directory. The container runs the API with Uvicorn on port 8000.

### Model: Where does it come from at startup?

At startup, the API loads the existing artifacts/model.joblib and artifacts/model-metadata.json files. It checks that the model's SHA-256 hash matches the metadata and that the feature list matches the expected features. The API does not train a new model.

### Ready: When do you call the service ready?

The service is ready when its startup process has loaded and verified the model successfully, and the /health endpoint returns HTTP 200 with "status": "ok" and the model version.

### Broken: What does it say if the model is missing?

If the model or metadata is missing, or the model checks fail, the API treats the model as unavailable. The /health and /predict endpoints return HTTP 503 with the detail "model unavailable".

### Log line: What must one request tell an operator?

A useful log line should tell the operator what happened, where it happened, and enough context to diagnose the issue. For a deployment request, include the endpoint or operation, the outcome or HTTP status, and a request ID to trace the request across logs. Never include secrets or sensitive request data.

### Secrets: What must never appear in a log?

Logs must never contain passwords, access tokens, API keys, credentials, or other sensitive personal information. Log only the information needed to diagnose and monitor the service.

### Identity: Which ID shows which model is running?

The model_version field identifies the model version returned by /health and /predict. The metadata also contains a model_run_id identifying the MLflow run associated with the model.

### Expected: Who knows the expected model, and when?

The deployment verification script knows the expected model because the operator provides it using --expected-model. This value is supplied when running the verification command, so the script can compare the deployed model against the model that was intended to be deployed.

### Promise: What does "deployed" promise to others?

A deployed service should expose a predictable HTTP API, validate prediction requests, return predictions from the verified saved model, and report whether the model is available. Deployment alone does not guarantee prediction accuracy or availability under every failure condition.

### Failure: Break it once. What does it leave behind?

A controlled failure test should document the failure, the HTTP response, the relevant logs, and the state of the service afterward. For example, if the model is unavailable at startup, the API should return HTTP 503 from /health and /predict. The exact remaining container, image, and log state must be confirmed from the actual test.

## Lab 5 — Cloud Run Deployment and Verification

### Deployment overview

The Bike Demand API is deployed on Google Cloud Run using a Docker image built by Google Cloud Build.

Deployment configuration:

- **Google Cloud project:** `mlops-demo-512323`
- **Cloud Run service:** `mlops-fri2-teama-bike-demand`
- **Cloud Run region:** `europe-west1`
- **Container port:** `8000`
- **Build configuration:** `cloudbuild.yaml` at the repository root
- **Dockerfile:** `bike-demand/Dockerfile`
- **Container registry:** Google Artifact Registry (`cloud-run-source-deploy`)
- **Git branch used for deployment:** `main`

The Cloud Build trigger runs the following steps:

1. Build the Docker image from the `bike-demand/` directory.
2. Pass the Git commit SHA to Docker using the `BIKE_DEMAND_REVISION` build argument.
3. Push the tagged image to Artifact Registry.
4. Deploy the image to the existing Cloud Run service.

The deployed application loads the saved model artifacts at startup. It does not retrain the model when handling HTTP requests.

### Deployment identity and readiness

The `GET /health` endpoint reports whether the model is ready and identifies both the deployed model and the application code revision.

A successful response observed during Lab 5 was:

```json
{
  "status": "ok",
  "model_version": "baseline-f01a22df4c39",
  "code_revision": "224b177c55ad19474804899da0e59b7f59864bc2"
}
```

The `model_version` identifies the saved machine learning model. The `code_revision` identifies the Git commit used to build the deployed application.

The code revision is injected during the Docker build using:

```bash
docker build \
  --build-arg BIKE_DEMAND_REVISION=$COMMIT_SHA \
  -t IMAGE_NAME \
  -f Dockerfile \
  .
```

The SHA shown above is an example from a verified deployment. It will change when a different Git commit is deployed.

### Accessing the private Cloud Run service

The Cloud Run service requires authentication. Anonymous HTTP requests are not permitted.

On Windows PowerShell, an authenticated health check can be performed with:

```powershell
$URL = "https://mlops-fri2-teama-bike-demand-709271018248.europe-west1.run.app"
$TOKEN = gcloud.cmd auth print-identity-token

Invoke-RestMethod -Uri "$URL/health" -Headers @{Authorization = "Bearer $TOKEN"}
```

The Google Cloud CLI must be installed and authenticated with an account authorized to invoke the service.

Access tokens must not be committed to Git or written to application logs.

### External deployment verification

The repository includes `bike-demand/scripts/verify_deployment.py`.

This script sends an HTTP request to `/health` and checks:

- HTTP status code is `200`.
- Application status is `ok`.
- The observed model version matches the expected model version.
- The observed code revision matches the expected Git revision.

The script prints `Deployment verification PASSED` and exits with code `0` when all checks succeed. Otherwise, it prints `Deployment verification FAILED` and exits with code `1`.

Because the deployed Cloud Run service is private, a local authenticated proxy can be used without modifying the verification script.

Start the proxy in one PowerShell terminal:

```powershell
gcloud.cmd run services proxy mlops-fri2-teama-bike-demand --project mlops-demo-512323 --region europe-west1 --port 8080
```

Keep this terminal open while running the verification commands.

From the repository root, in a second PowerShell terminal, run the successful verification:

```powershell
python .\bike-demand\scripts\verify_deployment.py --url http://127.0.0.1:8080 --expected-model baseline-f01a22df4c39 --expected-revision 224b177c55ad19474804899da0e59b7f59864bc2
```

Expected final output:

```text
Deployment verification PASSED
```

A deliberate failure can be tested by providing an incorrect expected model version:

```powershell
python .\bike-demand\scripts\verify_deployment.py --url http://127.0.0.1:8080 --expected-model mauvaise-version --expected-revision 224b177c55ad19474804899da0e59b7f59864bc2
```

Expected final output:

```text
Deployment verification FAILED
```

This negative test does not modify the deployed model or application. It demonstrates that the verifier correctly detects a version mismatch.

For future deployments, replace the example SHA with the actual revision returned by `/health`.

### Structured application logs

The API produces structured JSON logs for HTTP requests.

An observed log entry from the deployed service was:

```json
{
  "event": "http_request",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "latency_ms": 4.89,
  "request_id": "26be6487-b32f-4bba-b35a-a66083886bdf",
  "model_version": "baseline-f01a22df4c39",
  "code_revision": "224b177c55ad19474804899da0e59b7f59864bc2"
}
```

These fields make it possible to identify the requested endpoint, HTTP result, processing time, request identifier, model version, and deployed code revision.

To inspect these logs:

1. Open Google Cloud Console.
2. Navigate to **Cloud Run**.
3. Select the `mlops-fri2-teama-bike-demand` service.
4. Open **Logs**.
5. Find a request to `/health` and expand the corresponding structured application log entry.

Application logs must not contain passwords, access tokens, API keys, or raw sensitive request data.

### Security and cost considerations

The service is configured to require authenticated access rather than allowing anonymous public invocation.

The local Cloud Run proxy should be stopped after verification by pressing `Ctrl+C` in the terminal running the proxy.

Cloud Run scaling settings, including minimum and maximum instances, should be reviewed to avoid unnecessary resource usage. The service should remain available only as long as required for project evaluation.

### Lab 5 verification evidence

The team collected the following deployment evidence:

1. A successful `/health` response showing `status`, `model_version`, and the deployed Git SHA.
2. A structured JSON request log from Cloud Run containing `request_id`, `latency_ms`, `model_version`, and `code_revision`.
3. External verification results demonstrating both a successful deployment check (`PASSED`) and a deliberate model-version mismatch (`FAILED`).

Together, these checks demonstrate that the deployed service is reachable by authorized users, exposes its deployment identity, produces traceable request logs, and detects incorrect deployment versions.
