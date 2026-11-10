# Release v1.0.0: Bike Demand service

Team A (fri2): Alexandre, Thaddée, Alban, Nicolas. Hourly bike rental demand from calendar and weather features (UCI Bike Sharing), served as a private FastAPI service on Cloud Run.

## What this release contains

| Item | Where |
|---|---|
| Code | this tag's commit on `main` |
| Configuration | `bike-demand/configs/baseline.yaml` (model settings), `bike-demand/configs/gate-policy.yaml` (gate policy v1), `bike-demand/configs/candidates/` |
| Accepted model | `baseline-f01a22df4c39`, sha256 `fd98ceafc57a5babce61ce703cbf9cb8d1f83c6820b0b34fe30ad1a0fc49c304`; bundle in `gs://mlops-fri2-teama-bike-demand-models/bundles/baseline-f01a22df4c39/`; pointer `bike-demand/registry/accepted.json` |
| Data | frozen `data/raw/hour.csv`, sha256 `e03de4ee…` (checked by preflight against `data/manifest.json`) |
| Environment | `bike-demand/uv.lock`, `bike-demand/Dockerfile` (`app` and `service` stages) |
| Checks | GitHub Actions (`.github/workflows/ci.yml`) on every PR; Cloud Build (`cloudbuild.yaml`) on every merge to `main`: bundle digests, tests, built-image identity check, deploy without traffic, switch |
| Gate decisions | `bike-demand/decisions/`, raw runs in `bike-demand/reports/evidence/lab7-*` |
| Incident and recovery | `bike-demand/reports/lab8-incident.md`, raw evidence in `bike-demand/reports/evidence/lab8-*` |
| Docs | `README.md`, `RUNBOOK.md`, team reports `bike-demand/reports/week-0*-team.md` |

## Final held-test result

Scored once, on 2026-11-10, on the model already selected through the gate. It was never used to choose a model. Raw record: `bike-demand/reports/evidence/heldtest-v1.0.0.json`, produced by `bike-demand/scripts/evaluate_held_test.py` at commit `b294696`.

| Period | Rows | Accepted model MAE | Train-mean baseline MAE | Mean label |
|---|---|---|---|---|
| Validation (Jan–Jun 2012) | 4,358 | 86.85 | 154.23 | 215.2 |
| **Held test (Jul–Dec 2012)** | **4,376** | **93.74** | **182.21** | 254.1 |

**Reading the result:**

- The held-test error is higher than on validation in absolute terms.
- The second half of 2012 was also busier (mean 254 vs 215 bikes/hour), so relative to demand the error is similar (about 37% vs 40% of the mean).
- The model halves the error of the naive baseline in both periods.

## Known limitations

- **Live check:** the live identity check on the private URL is run from a laptop; Cloud Build checks the built image before deploy because it cannot mint identity tokens with our IAM.
- **Delivery path:** delivery uses Cloud Build with its service account, without a stored key, not GitHub OIDC with Workload Identity Federation, which our IAM refused.
- **Single accepted version:** the Lab 7 gate rejected all three candidates, and the baseline was retained.
- **Monitoring and latency:** the replay monitor uses a fixed validation sample, not real traffic. Latency figures are from a laptop.
- **Future data:** one validation half-year and one test half-year cannot represent later years or other cities.
