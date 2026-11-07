"""Record the accepted model's predictions on this machine, to compare across OSes.

Justifies the regression-test tolerance with measured cross-environment variation:
run it on two machines and compare validation_predictions_sha256 (identical means
byte-identical predictions on all 4,358 validation rows).

Run from bike-demand/ with the accepted bundle in artifacts/:
    uv run --locked python scripts/measure_prediction_drift.py
"""

import hashlib
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from bike_demand.promote import REFERENCE_INPUT
from bike_demand.split import split_data
from bike_demand.validate import FEATURES, load_data


def main() -> None:
    metadata = json.loads(Path("artifacts/model-metadata.json").read_text())
    model = joblib.load("artifacts/model.joblib")
    validation = split_data(load_data(Path("data/raw/hour.csv")))["validation"]
    predictions = np.asarray(
        model.predict(validation.loc[:, list(FEATURES)]), dtype=np.float64
    )
    reference = pd.DataFrame(
        [[REFERENCE_INPUT[f] for f in FEATURES]], columns=list(FEATURES)
    )
    print(
        json.dumps(
            {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "scikit_learn": sklearn.__version__,
                "model_version": metadata["model_version"],
                "reference_prediction": repr(float(model.predict(reference)[0])),
                "validation_rows": len(predictions),
                "validation_predictions_sha256": hashlib.sha256(
                    predictions.tobytes()
                ).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
