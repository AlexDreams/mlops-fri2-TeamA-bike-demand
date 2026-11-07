"""The replay monitor counts good attempts, failures and rejections correctly."""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "monitor_replay.py"


class Service(BaseHTTPRequestHandler):
    """Stand-in service: fails rainy hours (weathersit 3) with HTTP 500."""

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(200, {"status": "ok", "model_version": "m-1"})

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if request["hr"] > 23:
            self.reply(422, {"detail": "hr"})
        elif request["weathersit"] == 3:
            self.reply(500, {"detail": "boom"})
        else:
            self.reply(200, {"prediction": 100.0, "model_version": "m-1"})

    def log_message(self, *args):
        pass


def test_success_rate_separates_failures_from_rejections(tmp_path):
    # Catches: counting intentional 422 rejections as failures, or a 500 on a
    # valid request as success.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Service)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--url",
                f"http://127.0.0.1:{server.server_port}",
                "--out",
                str(tmp_path / "out"),
                "--every",
                "50",
                "--invalid",
                "3",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
    finally:
        server.shutdown()
        server.server_close()
    summary = json.loads((tmp_path / "out/summary.json").read_text())
    events = (tmp_path / "out/events.jsonl").read_text().splitlines()

    failed = summary["eligible_status_counts"].get("500", 0)
    assert failed > 0
    assert summary["good_eligible_attempts"] == summary["eligible_attempts"] - failed
    assert summary["success_rate"] < 1
    assert summary["invalid_probes"] == 3
    assert summary["invalid_probes_rejected_422"] == 3
    assert len(events) == summary["eligible_attempts"] + 3
    assert "Bearer" not in result.stdout
