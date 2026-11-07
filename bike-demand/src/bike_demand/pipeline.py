"""Single entry point: train one declared candidate, evaluate it, record a decision.

Run from bike-demand/:
    uv run --locked python -m bike_demand.pipeline --candidate configs/candidates/X.yaml

Exit codes: 0 eligible, 1 rejected, 2 blocked, 3 failed before any decision.
The pipeline never changes registry/accepted.json or the served model.
"""

import argparse
import json
from pathlib import Path

from bike_demand.candidate import train_candidate
from bike_demand.gate import EXIT_CODES, evaluate, write_decision


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=Path("configs/gate-policy.yaml"))
    parser.add_argument("--accepted", type=Path, default=Path("registry/accepted.json"))
    parser.add_argument("--bundles", type=Path, default=Path("bundles"))
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--decisions", type=Path, default=Path("decisions"))
    args = parser.parse_args()
    root = Path.cwd()

    try:
        run_dir = train_candidate(root, args.candidate, args.runs)
        decision = evaluate(root, run_dir, args.accepted, args.bundles, args.policy)
        path = write_decision(args.decisions, decision)
    except (ValueError, OSError, KeyError) as error:
        # Nothing was accepted or recorded; safe to fix the cause and rerun.
        print(f"Pipeline failed before a decision: {error}")
        return 3

    print(
        json.dumps(
            {
                "decision": path.as_posix(),
                "outcome": decision["outcome"],
                "candidate": decision["candidate"]["model_version"],
                "incumbent": decision["incumbent"]["model_version"],
                "evaluation": decision["evaluation"],
                "reasons": decision["reasons"],
            },
            indent=2,
        )
    )
    return EXIT_CODES[decision["outcome"]]


if __name__ == "__main__":
    raise SystemExit(main())
