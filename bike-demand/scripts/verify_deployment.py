"""Verify a running Bike Demand deployment over HTTP.

For a private Cloud Run service, put an identity token in the
BIKE_DEMAND_ID_TOKEN environment variable; it is sent as a Bearer token and
never printed.
"""

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a running Bike Demand service."
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Base URL of the running service",
    )
    parser.add_argument(
        "--expected-model",
        required=True,
        help="Expected model_version",
    )
    parser.add_argument(
        "--expected-revision",
        required=True,
        help="Expected deployed code revision",
    )
    args = parser.parse_args()

    health_url = args.url.rstrip("/") + "/health"
    token = os.environ.get("BIKE_DEMAND_ID_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        with urlopen(Request(health_url, headers=headers), timeout=10) as response:
            status_code = response.status
            health = json.load(response)
    except HTTPError as exc:
        print(f"FAIL: /health returned HTTP {exc.code}")
        return 1
    except (URLError, TimeoutError, ValueError) as exc:
        print(f"FAIL: cannot verify /health: {exc}")
        return 1

    checks = [
        ("HTTP status", 200, status_code),
        ("readiness", "ok", health.get("status")),
        ("model_version", args.expected_model, health.get("model_version")),
        ("code_revision", args.expected_revision, health.get("code_revision")),
    ]

    failed = False

    for name, expected, observed in checks:
        result = "OK" if expected == observed else "FAIL"
        print(f"{name}: expected={expected!r}, observed={observed!r} -> {result}")
        if expected != observed:
            failed = True

    if failed:
        print("Deployment verification FAILED")
        return 1

    print("Deployment verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
