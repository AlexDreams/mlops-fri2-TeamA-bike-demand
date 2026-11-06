"""Candidate training: settings guard, isolated output, no partial bundles."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from bike_demand import candidate
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMALL = {"n_estimators": 10, "max_depth": 3, "random_state": 42, "n_jobs": 1}


def write_config(path: Path, model: dict, features=None) -> Path:
    config = {
        "data": "data/raw/hour.csv",
        "features": list(FEATURES) if features is None else features,
        "model": model,
    }
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def test_candidate_bundle_is_isolated_and_identified(tmp_path):
    # Catches: training that writes into artifacts/ (the served model) or a
    # bundle whose recorded digest does not match its bytes.
    served = PROJECT_ROOT / "artifacts/model.joblib"
    before = sha256(served) if served.exists() else None

    config = write_config(tmp_path / "small.yaml", SMALL)
    run_dir = candidate.train_candidate(PROJECT_ROOT, config, tmp_path / "runs")

    bundle = run_dir / "candidate"
    metadata = json.loads((bundle / "model-metadata.json").read_text())
    assert metadata["model_sha256"] == sha256(bundle / "model.joblib")
    assert metadata["features"] == list(FEATURES)
    assert metadata["config"]["model"] == SMALL
    assert metadata["partitions"]["train"]["rows"] == 8645
    assert (sha256(served) if served.exists() else None) == before


@pytest.mark.parametrize(
    "model",
    [
        {**SMALL, "max_features": "sqrt"},  # setting outside the allowed list
        {**SMALL, "n_estimators": 5000},  # outside the declared budget
        {**SMALL, "max_depth": True},  # bool is not an integer setting
        {**SMALL, "random_state": 7},  # fixed seed changed
    ],
)
def test_settings_guard_rejects(tmp_path, model):
    # Catches: a candidate changing more than the reviewed model settings.
    config = write_config(tmp_path / "bad.yaml", model)
    with pytest.raises(ValueError, match="candidate config"):
        candidate.load_candidate_config(config)


def test_feature_contract_cannot_change(tmp_path):
    # Catches: a candidate dropping or reordering the twelve contract predictors.
    config = write_config(tmp_path / "bad.yaml", SMALL, list(reversed(FEATURES)))
    with pytest.raises(ValueError, match="ordered features"):
        candidate.load_candidate_config(config)


def test_tracked_changes_ignores_untracked_records(tmp_path):
    # Catches: an uncommitted code change passing as a clean checkout, or a
    # pending decision record blocking every later run.
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    assert candidate.tracked_changes(tmp_path) is None  # not a repository
    subprocess.run([*git, "init", "-q"], check=True)
    (tmp_path / "code.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "code.py"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    (tmp_path / "decision.json").write_text("{}")
    assert candidate.tracked_changes(tmp_path) is False
    (tmp_path / "code.py").write_text("x = 2\n")
    assert candidate.tracked_changes(tmp_path) is True


def test_crash_leaves_no_finished_run(tmp_path, monkeypatch):
    # Catches: an interrupted run that leaves a directory the gate could use.
    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(candidate.joblib, "dump", fail)
    config = write_config(tmp_path / "small.yaml", SMALL)
    with pytest.raises(OSError):
        candidate.train_candidate(PROJECT_ROOT, config, tmp_path / "runs")
    finished = [p for p in (tmp_path / "runs").iterdir() if p.suffix != ".partial"]
    assert finished == []
