"""Accepted-state commands: fetch the accepted bundle, or promote an eligible one.

Run from bike-demand/:
    uv run --locked python -m bike_demand.promote fetch
    uv run --locked python -m bike_demand.promote promote --decision decisions/X.json

Bundles live in Cloud Storage at <bucket>/bundles/<model_version>/ and are never
overwritten. registry/accepted.json (committed, reviewed) names the accepted
version, its digests and the version it replaced.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import joblib
import pandas as pd

from bike_demand.preflight import sha256
from bike_demand.tracking import timestamp

BUNDLE_FILES = ("model.joblib", "model-metadata.json")
DEFAULT_BUCKET = "gs://mlops-fri2-teama-bike-demand-models"
# Fixed input whose prediction is recorded at promotion and checked by
# tests/test_model_regression.py for the accepted model.
REFERENCE_INPUT = {
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


def gcloud(*args: str) -> None:
    executable = shutil.which(os.environ.get("GCLOUD", "gcloud"))
    if executable is None:
        raise OSError("gcloud not found; install the Google Cloud CLI or set GCLOUD")
    subprocess.run([executable, *args], check=True)


def copy_from(uri: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in BUNDLE_FILES:
        gcloud("storage", "cp", f"{uri}{name}", str(destination / name))


def upload_once(bundle: Path, uri: str) -> None:
    """Upload without overwriting, then re-download and compare the bytes."""
    for name in BUNDLE_FILES:
        gcloud("storage", "cp", "--no-clobber", str(bundle / name), f"{uri}{name}")
    with tempfile.TemporaryDirectory(prefix="bike-promote-") as temporary:
        copy_from(uri, Path(temporary))
        for name in BUNDLE_FILES:
            if sha256(Path(temporary) / name) != sha256(bundle / name):
                raise ValueError(f"promote: {uri}{name} differs from the local bundle")


def reference_prediction(model_path: Path, features: list[str]) -> float:
    model = joblib.load(model_path)
    row = pd.DataFrame([[REFERENCE_INPUT[f] for f in features]], columns=features)
    return float(model.predict(row)[0])


def fetch(accepted_path: Path, bundles_dir: Path, copy=copy_from) -> Path:
    """Download the accepted bundle and verify it against the committed digests."""
    accepted = json.loads(accepted_path.read_text())
    destination = bundles_dir / accepted["model_version"]
    copy(accepted["uri"], destination)
    if sha256(destination / "model.joblib") != accepted["model_sha256"]:
        raise ValueError("fetch: model bytes do not match registry/accepted.json")
    if sha256(destination / "model-metadata.json") != accepted["metadata_sha256"]:
        raise ValueError("fetch: metadata bytes do not match registry/accepted.json")
    return destination


def promote(
    decision_path: Path, accepted_path: Path, bucket: str, upload=upload_once
) -> dict:
    """Upload the exact eligible bundle, then move the accepted pointer.

    Order matters: if anything stops before the last line, accepted.json is
    unchanged and the service keeps serving the previous accepted version.
    """
    decision = json.loads(decision_path.read_text())
    if decision.get("outcome") != "eligible":
        raise ValueError(f"promote: decision outcome is {decision.get('outcome')!r}")
    accepted = json.loads(accepted_path.read_text())
    if (
        decision["incumbent"]["model_version"] != accepted["model_version"]
        or decision["incumbent"]["model_sha256"] != accepted["model_sha256"]
    ):
        raise ValueError("promote: accepted model changed since the decision; rerun")

    bundle = Path(decision["candidate"]["path"])
    model_path = bundle / "model.joblib"
    metadata_path = bundle / "model-metadata.json"
    if sha256(model_path) != decision["candidate"]["model_sha256"]:
        raise ValueError("promote: candidate bytes differ from the evaluated bytes")
    metadata = json.loads(metadata_path.read_text())
    version = decision["candidate"]["model_version"]
    if metadata.get("model_version") != version:
        raise ValueError("promote: candidate metadata names another version")

    uri = f"{bucket.rstrip('/')}/bundles/{version}/"
    upload(bundle, uri)
    new = {
        "model_version": version,
        "model_sha256": decision["candidate"]["model_sha256"],
        "metadata_sha256": sha256(metadata_path),
        "uri": uri,
        "reference_prediction": reference_prediction(model_path, metadata["features"]),
        "accepted_at": timestamp(),
        "decision": decision_path.as_posix(),
        "previous": {
            key: accepted[key]
            for key in ("model_version", "model_sha256", "metadata_sha256", "uri")
        },
    }
    temporary = accepted_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(new, indent=2) + "\n")
    temporary.replace(accepted_path)
    return new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "promote"))
    parser.add_argument("--accepted", type=Path, default=Path("registry/accepted.json"))
    parser.add_argument("--bundles", type=Path, default=Path("bundles"))
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            print(f"Accepted bundle verified in {fetch(args.accepted, args.bundles)}")
        else:
            if args.decision is None:
                parser.error("promote requires --decision")
            new = promote(args.decision, args.accepted, args.bucket)
            print(json.dumps(new, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"{args.command} failed, accepted state unchanged: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
