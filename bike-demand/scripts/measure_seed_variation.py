"""Measure how much validation MAE moves when only the seed changes.

Uses the ACCEPTED model settings (configs/baseline.yaml), never a candidate, so the
gate margin can be justified before any candidate is evaluated.

Run from bike-demand/:
    uv run --locked python scripts/measure_seed_variation.py
"""

import json
import statistics
from pathlib import Path

import yaml
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

from bike_demand.split import split_data
from bike_demand.validate import FEATURES, load_data

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def main() -> None:
    settings = yaml.safe_load(Path("configs/baseline.yaml").read_text())["model"]
    partitions = split_data(load_data(Path("data/raw/hour.csv")))
    train, validation = partitions["train"], partitions["validation"]
    maes = []
    for seed in SEEDS:
        model = RandomForestRegressor(**{**settings, "random_state": seed})
        model.fit(train.loc[:, list(FEATURES)], train["cnt"])
        maes.append(
            float(
                mean_absolute_error(
                    validation["cnt"], model.predict(validation.loc[:, list(FEATURES)])
                )
            )
        )
    print(
        json.dumps(
            {
                "settings": settings,
                "seeds": list(SEEDS),
                "validation_mae": maes,
                "spread_max_minus_min": max(maes) - min(maes),
                "stdev": statistics.stdev(maes),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
