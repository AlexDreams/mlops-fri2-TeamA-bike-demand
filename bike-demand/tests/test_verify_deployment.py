"""Test the external deployment verification script."""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_deployment.py"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return

        body = json.dumps(
            {
                "status": "ok",
                "model_version": "baseline-f01a22df4c39",
                "code_revision": "abc123",
            }
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def run_verifier(expected_model, expected_revision):
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--url",
                f"http://127.0.0.1:{server.server_port}",
                "--expected-model",
                expected_model,
                "--expected-revision",
                expected_revision,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_matching_deployment_passes():
    result = run_verifier("baseline-f01a22df4c39", "abc123")
    assert result.returncode == 0
    assert "Deployment verification PASSED" in result.stdout


def test_wrong_model_fails():
    result = run_verifier("wrong-model", "abc123")
    assert result.returncode == 1
    assert "model_version" in result.stdout
    assert "FAIL" in result.stdout


def test_wrong_revision_fails():
    result = run_verifier("baseline-f01a22df4c39", "wrong-revision")
    assert result.returncode == 1
    assert "code_revision" in result.stdout
    assert "FAIL" in result.stdout
