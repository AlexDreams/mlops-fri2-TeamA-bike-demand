"""Promotion and fetch: only eligible exact bytes move the accepted pointer."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from bike_demand import promote
from bike_demand.candidate import train_candidate
from bike_demand.preflight import sha256
from bike_demand.validate import FEATURES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMALL = {"n_estimators": 10, "max_depth": 3, "random_state": 42, "n_jobs": 1}
OLD = {
    "model_version": "old-1",
    "model_sha256": "a" * 64,
    "metadata_sha256": "b" * 64,
    "uri": "gs://bucket/bundles/old-1/",
}


@pytest.fixture
def setup(tmp_path):
    config = tmp_path / "c.yaml"
    config.write_text(
        yaml.safe_dump(
            {"data": "data/raw/hour.csv", "features": list(FEATURES), "model": SMALL}
        )
    )
    run_dir = train_candidate(PROJECT_ROOT, config, tmp_path / "runs")
    metadata = json.loads((run_dir / "candidate/model-metadata.json").read_text())
    accepted = tmp_path / "accepted.json"
    accepted.write_text(json.dumps(OLD))
    decision = tmp_path / "decision.json"
    decision.write_text(
        json.dumps(
            {
                "outcome": "eligible",
                "candidate": {
                    "model_version": metadata["model_version"],
                    "model_sha256": metadata["model_sha256"],
                    "path": (run_dir / "candidate").as_posix(),
                },
                "incumbent": {
                    "model_version": OLD["model_version"],
                    "model_sha256": OLD["model_sha256"],
                },
            }
        )
    )
    uploads = []
    return decision, accepted, run_dir, metadata, uploads


def fake_upload(uploads):
    return lambda bundle, uri: uploads.append((bundle, uri))


def test_eligible_promotion_moves_pointer_and_keeps_previous(setup):
    decision, accepted, run_dir, metadata, uploads = setup
    new = promote.promote(decision, accepted, "gs://bucket", fake_upload(uploads))
    version = metadata["model_version"]
    assert uploads == [(run_dir / "candidate", f"gs://bucket/bundles/{version}/")]
    saved = json.loads(accepted.read_text())
    assert saved == new
    assert saved["model_version"] == version
    assert saved["previous"] == OLD
    assert isinstance(saved["reference_prediction"], float)


@pytest.mark.parametrize("outcome", ["rejected", "blocked"])
def test_non_eligible_decision_changes_nothing(setup, outcome):
    # Catches: a rejected or blocked candidate replacing the accepted model.
    decision, accepted, _, _, uploads = setup
    record = json.loads(decision.read_text())
    decision.write_text(json.dumps({**record, "outcome": outcome}))
    before = accepted.read_bytes()
    with pytest.raises(ValueError, match="outcome"):
        promote.promote(decision, accepted, "gs://bucket", fake_upload(uploads))
    assert accepted.read_bytes() == before
    assert uploads == []


def test_changed_incumbent_refuses(setup):
    # Catches: promoting against an accepted model that changed after evaluation.
    decision, accepted, _, _, uploads = setup
    accepted.write_text(json.dumps({**OLD, "model_version": "someone-else"}))
    with pytest.raises(ValueError, match="changed since the decision"):
        promote.promote(decision, accepted, "gs://bucket", fake_upload(uploads))
    assert uploads == []


def test_bytes_changed_after_decision_refuses(setup):
    # Catches: promoting bytes that differ from the ones the gate evaluated.
    decision, accepted, run_dir, _, uploads = setup
    with (run_dir / "candidate/model.joblib").open("ab") as stream:
        stream.write(b"x")
    with pytest.raises(ValueError, match="evaluated bytes"):
        promote.promote(decision, accepted, "gs://bucket", fake_upload(uploads))
    assert uploads == []


def test_fetch_rejects_wrong_bytes(setup, tmp_path):
    # Catches: serving or evaluating a downloaded bundle that is not the accepted one.
    _, _, run_dir, metadata, _ = setup
    accepted = tmp_path / "accepted-real.json"
    accepted.write_text(
        json.dumps(
            {
                **OLD,
                "model_version": metadata["model_version"],
                "model_sha256": metadata["model_sha256"],
                "metadata_sha256": sha256(run_dir / "candidate/model-metadata.json"),
            }
        )
    )

    def good_copy(uri, destination):
        shutil.copytree(run_dir / "candidate", destination, dirs_exist_ok=True)

    def bad_copy(uri, destination):
        good_copy(uri, destination)
        (destination / "model.joblib").write_bytes(b"not the model")

    assert promote.fetch(accepted, tmp_path / "ok", good_copy).is_dir()
    with pytest.raises(ValueError, match="model bytes"):
        promote.fetch(accepted, tmp_path / "bad", bad_copy)
