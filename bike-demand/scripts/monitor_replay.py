"""Replay validation-period requests to a running service and summarise its signals.

The same definitions are used for the baseline, incident and recovery periods (Lab 8):

- eligible attempt: a valid /predict request built from one validation-period row
  (2012-01-01..2012-06-30), every --every-th row in time order;
- good eligible attempt: HTTP 200 with a finite, nonnegative prediction and a
  model_version;
- success rate = good eligible attempts / all eligible attempts, in the replay window;
- rejection probes: deliberately invalid requests (hr=24), expected HTTP 422, counted
  separately so intentional rejections never count as failures;
- quality: MAE of the good predictions against the rows' cnt labels (bikes/hour);
  labels are never sent to the service;
- latency: client-side milliseconds per eligible attempt (p50, p95).

Raw per-request events go to <out>/events.jsonl and the summary to <out>/summary.json.
For a private Cloud Run service, set BIKE_DEMAND_ID_TOKEN (never printed or saved).

Run from bike-demand/:
    uv run --locked python scripts/monitor_replay.py --url URL --out reports/evidence/X
"""

import argparse
import json
import math
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bike_demand.split import split_data
from bike_demand.validate import FEATURES, load_data

FLOATS = {"temp", "atemp", "hum", "windspeed"}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def call(url: str, token: str | None, body: dict | None = None) -> tuple:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    started = time.perf_counter()
    try:
        with urlopen(Request(url, data=data, headers=headers), timeout=15) as reply:
            status, payload = reply.status, json.load(reply)
    except HTTPError as error:
        status, payload = error.code, None
    except (URLError, TimeoutError, ValueError):
        status, payload = None, None
    return status, payload, round((time.perf_counter() - started) * 1000, 2)


def request_body(row) -> dict:
    return {f: float(row[f]) if f in FLOATS else int(row[f]) for f in FEATURES}


def is_good(status, payload) -> bool:
    if status != 200 or not isinstance(payload, dict):
        return False
    value = payload.get("prediction")
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
        and bool(payload.get("model_version"))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--every", type=int, default=20)
    parser.add_argument("--invalid", type=int, default=10)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    token = os.environ.get("BIKE_DEMAND_ID_TOKEN")

    validation = split_data(load_data(Path("data/raw/hour.csv")))["validation"]
    rows = validation.iloc[:: args.every]
    args.out.mkdir(parents=True, exist_ok=False)

    started = now()
    health_status, health_before, _ = call(f"{base}/health", token)
    events, errors, latencies, versions = [], [], [], {}
    good = 0
    with (args.out / "events.jsonl").open("w", encoding="utf-8") as stream:
        for index, row in rows.iterrows():
            status, payload, ms = call(f"{base}/predict", token, request_body(row))
            ok = is_good(status, payload)
            prediction = (
                payload.get("prediction") if isinstance(payload, dict) else None
            )
            version = (
                payload.get("model_version") if isinstance(payload, dict) else None
            )
            event = {
                "utc": now(),
                "kind": "eligible",
                "row": int(row["instant"]),
                "status": status,
                "good": ok,
                "latency_ms": ms,
                "prediction": prediction,
                "model_version": version,
            }
            stream.write(json.dumps(event) + "\n")
            events.append(event)
            latencies.append(ms)
            if ok:
                good += 1
                errors.append(abs(prediction - float(row["cnt"])))
                versions[version] = versions.get(version, 0) + 1
        probes = []
        invalid = request_body(rows.iloc[0]) | {"hr": 24}
        for _ in range(args.invalid):
            status, _, ms = call(f"{base}/predict", token, invalid)
            probe = {"utc": now(), "kind": "invalid_probe", "status": status}
            stream.write(json.dumps(probe | {"latency_ms": ms}) + "\n")
            probes.append(status)
    _, health_after, _ = call(f"{base}/health", token)

    statuses = {}
    for event in events:
        statuses[str(event["status"])] = statuses.get(str(event["status"]), 0) + 1
    ordered = sorted(latencies)
    summary = {
        "url": base,
        "window_utc": {"start": started, "end": now()},
        "population": (
            f"validation rows 2012-01-01..2012-06-30, every {args.every}th in time order"
        ),
        "health_before": {"status": health_status, "body": health_before},
        "health_after": health_after,
        "eligible_attempts": len(events),
        "good_eligible_attempts": good,
        "success_rate": good / len(events) if events else None,
        "eligible_status_counts": statuses,
        "model_versions_in_good_responses": versions,
        "validation_mae_bikes_per_hour": statistics.fmean(errors) if errors else None,
        "mean_prediction": (
            statistics.fmean(e["prediction"] for e in events if e["good"])
            if good
            else None
        ),
        "latency_ms_p50": statistics.median(ordered) if ordered else None,
        "latency_ms_p95": ordered[int(0.95 * (len(ordered) - 1))] if ordered else None,
        "invalid_probes": len(probes),
        "invalid_probes_rejected_422": sum(1 for s in probes if s == 422),
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
