"""Train one candidate bundle in its own run directory; never touch accepted state."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import joblib
import yaml
from sklearn.ensemble import RandomForestRegressor

from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import partition_summary, split_data
from bike_demand.tracking import timestamp, training_commit, write_json
from bike_demand.train import select_features
from bike_demand.validate import FEATURES, load_data

# Settings a candidate may vary, with inclusive integer bounds.
ALLOWED_SETTINGS = {
    "n_estimators": (10, 300),
    "max_depth": (2, 30),
    "min_samples_leaf": (1, 50),
}
# Settings every candidate must keep, so runs stay reproducible and comparable.
FIXED_SETTINGS = {"random_state": 42, "n_jobs": 1}


def tracked_changes(root: Path) -> bool | None:
    """True if tracked files differ from the commit; None if git is unavailable.

    Untracked outputs (earlier decision records awaiting commit) do not count:
    they cannot change the code or configuration that produced this run.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return bool(result.stdout.strip()) if result.returncode == 0 else None


def load_candidate_config(path: Path) -> dict:
    """Load a candidate config; only model settings may differ from the contract."""
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or set(config) != {"data", "features", "model"}:
        raise ValueError("candidate config: require data, features and model")
    if config["data"] != "data/raw/hour.csv":
        raise ValueError("candidate config: use the frozen data/raw/hour.csv snapshot")
    if config["features"] != list(FEATURES):
        raise ValueError("candidate config: require the contract's ordered features")
    model = config["model"]
    if not isinstance(model, dict):
        raise ValueError("candidate config: model must be a mapping")
    unknown = set(model) - set(ALLOWED_SETTINGS) - set(FIXED_SETTINGS)
    if unknown:
        raise ValueError(f"candidate config: settings not allowed {sorted(unknown)}")
    for key, value in FIXED_SETTINGS.items():
        if model.get(key) != value:
            raise ValueError(f"candidate config: {key} must be {value}")
    for key, (low, high) in ALLOWED_SETTINGS.items():
        if key in model:
            value = model[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(
                    f"candidate config: {key} must be an integer in [{low}, {high}]"
                )
    return config


def train_candidate(root: Path, config_path: Path, runs_dir: Path) -> Path:
    """Fit on the train window only and write an immutable candidate bundle.

    Output goes to runs_dir/<run_id>.partial/ and is renamed to runs_dir/<run_id>/
    only once complete, so a crash never leaves a bundle that looks finished.
    """
    config = load_candidate_config(config_path)
    frame = load_data(root / config["data"])
    snapshot = check_snapshot(root)
    partitions = split_data(frame)
    train = partitions["train"]
    # Validation and test rows are never seen here; the gate evaluates.
    model = RandomForestRegressor(**config["model"])
    model.fit(select_features(train, config["features"]), train["cnt"])

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{config_path.stem}-{uuid4().hex[:6]}"
    final = runs_dir / run_id
    partial = runs_dir / f"{run_id}.partial"
    bundle = partial / "candidate"
    bundle.mkdir(parents=True)

    model_path = bundle / "model.joblib"
    joblib.dump(model, model_path)
    metadata = {
        "model_version": f"rf-{uuid4().hex[:12]}",
        "run_id": run_id,
        "candidate_name": config_path.stem,
        "timestamp": timestamp(),
        "training_commit": training_commit(root),
        "working_tree_dirty": tracked_changes(root),
        "data_sha256": snapshot["sha256"],
        "features": config["features"],
        "partitions": partition_summary(partitions),
        "config": config,
        "config_sha256": sha256(config_path),
        "effective_model_settings": model.get_params(),
        "model_sha256": sha256(model_path),
    }
    write_json(bundle / "model-metadata.json", metadata)
    partial.rename(final)
    return final
