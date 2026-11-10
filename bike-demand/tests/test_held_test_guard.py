"""The held-test script refuses to run twice or on unverified bytes.

These tests stop at the guards, before any data is read: they never score the
held test period.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "evaluate_held_test.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_refuses_when_a_result_already_exists(tmp_path):
    # Catches: scoring the held test a second time (for example to compare models).
    out = tmp_path / "heldtest.json"
    out.write_text("{}")
    result = run("--out", out)
    assert result.returncode == 1
    assert "scored once" in result.stdout
    assert out.read_text() == "{}"


def test_refuses_bytes_that_do_not_match_the_pointer(tmp_path):
    # Catches: scoring a model other than the accepted one.
    bundle = tmp_path / "bundles" / "m-1"
    bundle.mkdir(parents=True)
    (bundle / "model.joblib").write_bytes(b"not the accepted model")
    (bundle / "model-metadata.json").write_text("{}")
    accepted = tmp_path / "accepted.json"
    accepted.write_text(
        json.dumps(
            {"model_version": "m-1", "model_sha256": "0" * 64, "metadata_sha256": "0"}
        )
    )
    out = tmp_path / "heldtest.json"
    result = run(
        "--accepted", accepted, "--bundles", tmp_path / "bundles", "--out", out
    )
    assert result.returncode == 1
    assert "digest" in result.stdout
    assert not out.exists()
