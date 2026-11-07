"""Evaluate a candidate against the naive baseline and the accepted model, then decide.

Outcomes:
- eligible: every integrity, quality and operation check passed;
- rejected: evidence is valid and complete, but a measured rule failed;
- blocked: required evidence is missing or invalid, so no rule was decided.
"""

import json
import math
import time
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.metrics import mean_absolute_error

from bike_demand.candidate import tracked_changes
from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import split_data
from bike_demand.tracking import timestamp, training_commit
from bike_demand.validate import FEATURES, load_data

EXIT_CODES = {"eligible": 0, "rejected": 1, "blocked": 2}
POLICY_NUMBERS = {
    "quality": (
        "max_ratio_to_naive",
        "min_improvement_vs_incumbent",
        "max_peak_regression",
    ),
    "operation": ("max_bundle_mb", "max_p95_predict_ms"),
    "integrity": ("expected_validation_rows",),
    "budget": ("max_candidates",),
}


def finite_number(value) -> bool:
    """Reject booleans, strings, NaN and infinities before any comparison."""
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def load_policy(path: Path) -> dict:
    policy = yaml.safe_load(path.read_text())
    if not isinstance(policy, dict) or policy.get("metric") != "validation_mae":
        raise ValueError("policy: metric must be validation_mae")
    for section, keys in POLICY_NUMBERS.items():
        for key in keys:
            if not finite_number(policy.get(section, {}).get(key)):
                raise ValueError(f"policy: {section}.{key} must be a finite number")
    peak = policy["quality"].get("peak_hours")
    if not peak or not all(type(h) is int and 0 <= h <= 23 for h in peak):
        raise ValueError("policy: quality.peak_hours must list hours in [0, 23]")
    if type(policy["integrity"].get("require_clean_checkout")) is not bool:
        raise ValueError("policy: integrity.require_clean_checkout must be true/false")
    return policy


def _check(checks: list, group: str, name: str, passed, observed, expected) -> bool:
    """Record one check. passed=None means the evidence was not available."""
    status = "missing" if passed is None else ("pass" if passed else "fail")
    checks.append(
        {
            "group": group,
            "name": name,
            "status": status,
            "observed": observed,
            "expected": expected,
        }
    )
    return passed is True


def _load_bundle(directory: Path, expected_sha: str | None):
    """Return (model, metadata) only if the bytes match a trusted digest."""
    model_path = directory / "model.joblib"
    metadata_path = directory / "model-metadata.json"
    if not (model_path.is_file() and metadata_path.is_file()):
        return None, None, None
    metadata = json.loads(metadata_path.read_text())
    actual = sha256(model_path)
    trusted = expected_sha if expected_sha is not None else metadata.get("model_sha256")
    if actual != trusted or actual != metadata.get("model_sha256"):
        return None, metadata, actual
    # Unpickle only after the digest matched a trusted record.
    return joblib.load(model_path), metadata, actual


def _p95_predict_ms(model, row) -> float:
    for _ in range(20):
        model.predict(row)
    timings = []
    for _ in range(200):
        started = time.perf_counter()
        model.predict(row)
        timings.append((time.perf_counter() - started) * 1000)
    return float(np.percentile(timings, 95))


def evaluate(
    root: Path,
    run_dir: Path,
    accepted_path: Path,
    bundles_dir: Path,
    policy_path: Path,
) -> dict:
    checks: list[dict] = []
    policy = load_policy(policy_path)
    accepted = json.loads(accepted_path.read_text())
    integrity = policy["integrity"]

    # Integrity: data, identity of both models, evaluation rows.
    try:
        snapshot = check_snapshot(root)
        data_ok = True
    except (ValueError, OSError) as error:
        snapshot, data_ok = None, False
        _check(checks, "integrity", "data_snapshot", False, str(error), "manifest")
    if data_ok:
        _check(
            checks, "integrity", "data_snapshot", True, snapshot["sha256"], "manifest"
        )

    evaluator = {
        "commit": training_commit(root),
        "working_tree_dirty": tracked_changes(root),
    }
    if integrity["require_clean_checkout"]:
        _check(
            checks,
            "integrity",
            "clean_checkout",
            evaluator["commit"] != "unavailable"
            and evaluator["working_tree_dirty"] is False,
            evaluator,
            {"commit": "known", "working_tree_dirty": False},
        )

    candidate, cand_meta, cand_sha = _load_bundle(run_dir / "candidate", None)
    _check(
        checks,
        "integrity",
        "candidate_bytes",
        None if cand_meta is None else candidate is not None,
        cand_sha,
        None if cand_meta is None else cand_meta.get("model_sha256"),
    )
    if cand_meta is not None:
        _check(
            checks,
            "integrity",
            "candidate_contract",
            cand_meta.get("features") == list(FEATURES)
            and data_ok
            and cand_meta.get("data_sha256") == snapshot["sha256"],
            {
                "features": cand_meta.get("features"),
                "data_sha256": cand_meta.get("data_sha256"),
            },
            {
                "features": list(FEATURES),
                "data_sha256": snapshot["sha256"] if data_ok else None,
            },
        )
        if integrity["require_clean_checkout"]:
            _check(
                checks,
                "integrity",
                "candidate_clean_checkout",
                cand_meta.get("training_commit") != "unavailable"
                and cand_meta.get("working_tree_dirty") is False,
                {
                    "commit": cand_meta.get("training_commit"),
                    "working_tree_dirty": cand_meta.get("working_tree_dirty"),
                },
                {"commit": "known", "working_tree_dirty": False},
            )

    incumbent_dir = bundles_dir / accepted["model_version"]
    incumbent, inc_meta, inc_sha = _load_bundle(incumbent_dir, accepted["model_sha256"])
    _check(
        checks,
        "integrity",
        "incumbent_bytes",
        None if inc_meta is None else incumbent is not None,
        inc_sha,
        accepted["model_sha256"],
    )
    if inc_meta is not None:
        _check(
            checks,
            "integrity",
            "incumbent_version",
            inc_meta.get("model_version") == accepted["model_version"],
            inc_meta.get("model_version"),
            accepted["model_version"],
        )

    evaluation: dict = {
        "window": "validation 2012-01-01..2012-06-30",
        "metric": "MAE, bikes per hour",
    }
    if data_ok:
        partitions = split_data(load_data(root / "data/raw/hour.csv"))
        train, validation = partitions["train"], partitions["validation"]
        _check(
            checks,
            "integrity",
            "validation_rows",
            len(validation) == integrity["expected_validation_rows"],
            len(validation),
            integrity["expected_validation_rows"],
        )
        evaluation["rows"] = len(validation)

    blocked = any(c["status"] != "pass" for c in checks)
    if not blocked:
        x_val = validation.loc[:, list(FEATURES)]
        y_val = validation["cnt"]
        cand_pred = candidate.predict(x_val)
        inc_pred = incumbent.predict(x_val)
        finite_ok = _check(
            checks,
            "integrity",
            "finite_predictions",
            bool(np.isfinite(cand_pred).all() and np.isfinite(inc_pred).all()),
            "checked",
            "all finite",
        )
        blocked = not finite_ok

    if not blocked:
        quality = policy["quality"]
        naive_mae = float(
            mean_absolute_error(y_val, np.full(len(y_val), float(train["cnt"].mean())))
        )
        cand_mae = float(mean_absolute_error(y_val, cand_pred))
        inc_mae = float(mean_absolute_error(y_val, inc_pred))
        peak = validation["hr"].isin(quality["peak_hours"]).to_numpy()
        cand_peak = float(mean_absolute_error(y_val[peak], cand_pred[peak]))
        inc_peak = float(mean_absolute_error(y_val[peak], inc_pred[peak]))
        evaluation.update(
            {
                "naive_mae": naive_mae,
                "candidate_mae": cand_mae,
                "incumbent_mae": inc_mae,
                "peak_rows": int(peak.sum()),
                "candidate_peak_mae": cand_peak,
                "incumbent_peak_mae": inc_peak,
            }
        )
        _check(
            checks,
            "quality",
            "beats_naive",
            cand_mae <= quality["max_ratio_to_naive"] * naive_mae,
            cand_mae,
            f"<= {quality['max_ratio_to_naive']} x naive ({naive_mae:.3f})",
        )
        _check(
            checks,
            "quality",
            "improves_on_accepted",
            cand_mae <= inc_mae - quality["min_improvement_vs_incumbent"],
            cand_mae,
            f"<= accepted {inc_mae:.3f} - {quality['min_improvement_vs_incumbent']}",
        )
        _check(
            checks,
            "quality",
            "peak_hours_no_regression",
            cand_peak <= inc_peak + quality["max_peak_regression"],
            cand_peak,
            f"<= accepted peak {inc_peak:.3f} + {quality['max_peak_regression']}",
        )

        operation = policy["operation"]
        size_mb = (
            sum(p.stat().st_size for p in (run_dir / "candidate").iterdir()) / 1_000_000
        )
        p95 = _p95_predict_ms(candidate, x_val.iloc[[0]])
        evaluation.update({"bundle_mb": size_mb, "p95_predict_ms": p95})
        _check(
            checks,
            "operation",
            "bundle_size",
            size_mb <= operation["max_bundle_mb"],
            size_mb,
            f"<= {operation['max_bundle_mb']} MB",
        )
        _check(
            checks,
            "operation",
            "p95_single_row_latency",
            p95 <= operation["max_p95_predict_ms"],
            p95,
            f"<= {operation['max_p95_predict_ms']} ms (local, warm, 200 calls)",
        )

    failed = [c for c in checks if c["status"] != "pass"]
    if blocked:
        outcome = "blocked"
    else:
        outcome = "rejected" if failed else "eligible"

    return {
        "decision_version": 1,
        "run_id": run_dir.name,
        "timestamp": timestamp(),
        "outcome": outcome,
        "reasons": [
            f"{c['group']}.{c['name']}: {c['status']} "
            f"(observed {c['observed']}, expected {c['expected']})"
            for c in failed
        ],
        "policy": {
            "path": policy_path.as_posix(),
            "sha256": sha256(policy_path),
            "policy_version": policy.get("policy_version"),
        },
        "candidate": {
            "model_version": None if cand_meta is None else cand_meta["model_version"],
            "model_sha256": cand_sha,
            "path": (run_dir / "candidate").as_posix(),
            "candidate_name": None
            if cand_meta is None
            else cand_meta["candidate_name"],
            "config_sha256": None if cand_meta is None else cand_meta["config_sha256"],
            "training_commit": None
            if cand_meta is None
            else cand_meta["training_commit"],
        },
        "incumbent": {
            "model_version": accepted["model_version"],
            "model_sha256": accepted["model_sha256"],
        },
        "evaluator": evaluator,
        "evaluation": evaluation,
        "checks": checks,
    }


def write_decision(decisions_dir: Path, decision: dict) -> Path:
    """Write a new decision record; never overwrite an existing one."""
    decisions_dir.mkdir(parents=True, exist_ok=True)
    path = decisions_dir / f"{decision['run_id']}.json"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(decision, indent=2, allow_nan=False) + "\n")
    return path
