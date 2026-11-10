"""Score the held test period ONCE, on the model already selected (Week 5).

The held test (2012-07-01..2012-12-31) was never used for training, tuning or the
gate. This script refuses to run if a result already exists, and refuses to load a
model whose bytes do not match registry/accepted.json. It also scores the train-mean
baseline on the same rows for context. It never chooses between models.

Run from bike-demand/, after `uv run --locked python -m bike_demand.promote fetch`:
    uv run --locked python scripts/evaluate_held_test.py
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error

from bike_demand.candidate import tracked_changes
from bike_demand.preflight import check_snapshot, sha256
from bike_demand.split import partition_summary, split_data
from bike_demand.tracking import timestamp, training_commit
from bike_demand.validate import FEATURES, load_data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted", type=Path, default=Path("registry/accepted.json"))
    parser.add_argument("--bundles", type=Path, default=Path("bundles"))
    parser.add_argument(
        "--out", type=Path, default=Path("reports/evidence/heldtest-v1.0.0.json")
    )
    args = parser.parse_args()

    # Guards run before any data is read.
    if args.out.exists():
        print(f"Refused: {args.out} exists; the held test is scored once.")
        return 1
    accepted = json.loads(args.accepted.read_text())
    bundle = args.bundles / accepted["model_version"]
    model_path = bundle / "model.joblib"
    if not model_path.is_file() or sha256(model_path) != accepted["model_sha256"]:
        print("Refused: model bytes missing or digest differs from accepted.json.")
        return 1
    if sha256(bundle / "model-metadata.json") != accepted["metadata_sha256"]:
        print("Refused: metadata digest differs from accepted.json.")
        return 1

    root = Path.cwd()
    snapshot = check_snapshot(root)
    partitions = split_data(load_data(root / "data/raw/hour.csv"))
    model = joblib.load(model_path)
    train_mean = float(partitions["train"]["cnt"].mean())
    scores = {}
    for name in ("validation", "test"):
        rows = partitions[name]
        predictions = model.predict(rows.loc[:, list(FEATURES)])
        if not np.isfinite(predictions).all():
            print(f"Refused: non-finite predictions on {name}.")
            return 1
        scores[name] = {
            "model_mae": float(mean_absolute_error(rows["cnt"], predictions)),
            "train_mean_mae": float(
                mean_absolute_error(rows["cnt"], np.full(len(rows), train_mean))
            ),
            "mean_label": float(rows["cnt"].mean()),
        }

    record = {
        "purpose": "single held-test evaluation of the selected model (Week 5)",
        "timestamp": timestamp(),
        "code_commit": training_commit(root),
        "tracked_changes": tracked_changes(root),
        "model_version": accepted["model_version"],
        "model_sha256": accepted["model_sha256"],
        "data_sha256": snapshot["sha256"],
        "partitions": partition_summary(partitions),
        "train_mean": train_mean,
        "metric": "MAE, bikes per hour",
        "scores": scores,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
