"""Gate: genuine rejection, blocked evidence, eligibility and safe records."""

import json
import shutil
from pathlib import Path

import pytest
import yaml

from bike_demand import gate
from bike_demand.candidate import train_candidate
from bike_demand.validate import FEATURES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SMALL = {"n_estimators": 10, "max_depth": 6, "random_state": 42, "n_jobs": 1}


def policy_file(tmp_path: Path, **quality) -> Path:
    policy = yaml.safe_load((PROJECT_ROOT / "configs/gate-policy.yaml").read_text())
    policy["quality"].update(quality)
    # Test runs are not official decisions; they run from a working tree.
    policy["integrity"]["require_clean_checkout"] = False
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(policy))
    return path


def make_run(tmp_path: Path, model: dict = SMALL) -> Path:
    config = tmp_path / "candidate.yaml"
    config.write_text(
        yaml.safe_dump(
            {"data": "data/raw/hour.csv", "features": list(FEATURES), "model": model}
        )
    )
    return train_candidate(PROJECT_ROOT, config, tmp_path / "runs")


def accept(tmp_path: Path, run_dir: Path) -> tuple[Path, Path]:
    """Make run_dir's bundle the accepted incumbent; return (accepted, bundles)."""
    metadata = json.loads((run_dir / "candidate/model-metadata.json").read_text())
    bundles = tmp_path / "bundles"
    shutil.copytree(run_dir / "candidate", bundles / metadata["model_version"])
    accepted = tmp_path / "accepted.json"
    accepted.write_text(
        json.dumps(
            {
                "model_version": metadata["model_version"],
                "model_sha256": metadata["model_sha256"],
            }
        )
    )
    return accepted, bundles


def test_same_model_is_rejected_with_reason(tmp_path):
    # Catches: a gate that promotes a candidate that does not beat the accepted
    # model by the committed margin (an "accepted equivalent").
    run_dir = make_run(tmp_path)
    accepted, bundles = accept(tmp_path, run_dir)
    decision = gate.evaluate(
        PROJECT_ROOT, run_dir, accepted, bundles, policy_file(tmp_path)
    )
    assert decision["outcome"] == "rejected"
    failed = {c["name"] for c in decision["checks"] if c["status"] != "pass"}
    assert failed == {"improves_on_accepted"}
    assert decision["evaluation"]["candidate_mae"] == pytest.approx(
        decision["evaluation"]["incumbent_mae"]
    )
    assert decision["evaluation"]["rows"] == 4358


def test_missing_incumbent_blocks_before_any_score(tmp_path):
    # Catches: treating unavailable incumbent evidence as a pass.
    run_dir = make_run(tmp_path)
    accepted, bundles = accept(tmp_path, run_dir)
    shutil.rmtree(bundles)
    decision = gate.evaluate(
        PROJECT_ROOT, run_dir, accepted, bundles, policy_file(tmp_path)
    )
    assert decision["outcome"] == "blocked"
    statuses = {c["name"]: c["status"] for c in decision["checks"]}
    assert statuses["incumbent_bytes"] == "missing"
    assert not any(c["group"] == "quality" for c in decision["checks"])


def test_tampered_candidate_blocks(tmp_path):
    # Catches: evaluating bytes other than the ones the training run recorded.
    run_dir = make_run(tmp_path)
    accepted, bundles = accept(tmp_path, run_dir)
    with (run_dir / "candidate/model.joblib").open("ab") as stream:
        stream.write(b"tampered")
    decision = gate.evaluate(
        PROJECT_ROOT, run_dir, accepted, bundles, policy_file(tmp_path)
    )
    assert decision["outcome"] == "blocked"
    assert "integrity.candidate_bytes: fail" in decision["reasons"][0]


def test_all_rules_passing_is_eligible(tmp_path):
    # Catches: a gate that can never say yes (a margin of -1000 always passes).
    run_dir = make_run(tmp_path)
    accepted, bundles = accept(tmp_path, run_dir)
    policy = policy_file(tmp_path, min_improvement_vs_incumbent=-1000)
    decision = gate.evaluate(PROJECT_ROOT, run_dir, accepted, bundles, policy)
    assert decision["outcome"] == "eligible"
    assert decision["reasons"] == []


@pytest.mark.parametrize("bad", [float("nan"), True, "2.0", None])
def test_policy_rejects_non_numbers(tmp_path, bad):
    # Catches: NaN, booleans or strings silently passing every comparison.
    path = policy_file(tmp_path)
    policy = yaml.safe_load(path.read_text())
    policy["quality"]["min_improvement_vs_incumbent"] = bad
    path.write_text(yaml.safe_dump(policy))
    with pytest.raises(ValueError, match="finite number"):
        gate.load_policy(path)


def test_decision_records_are_never_overwritten(tmp_path):
    # Catches: a rerun silently replacing an earlier decision record.
    decision = {"run_id": "run-1", "outcome": "rejected"}
    gate.write_decision(tmp_path, decision)
    with pytest.raises(FileExistsError):
        gate.write_decision(tmp_path, {**decision, "outcome": "eligible"})
