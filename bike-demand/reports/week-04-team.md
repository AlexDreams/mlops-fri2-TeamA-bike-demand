# Week 4, Labs 7–8: training pipeline with a gate, incident response

**Team report — Team A / Bike Demand.** Repository: https://github.com/AlexDreams/mlops-fri2-TeamA-bike-demand

## Lab 7 — Training pipeline, model evaluation and quality gate

### Outcome

All three declared candidates were **rejected** by the committed policy. The accepted model `baseline-f01a22df4c39` (sha256 `fd98ceaf…`) was **retained**; no promotion was made. This is the actual result, not a forced pass (slide 2).

### Contract and order of evidence

- **Policy first:** policy v1 in `bike-demand/configs/gate-policy.yaml` and the three candidates in `bike-demand/configs/candidates/` were merged to `main` in PR #41 on 2026-11-06 at 16:41 UTC.
- **Margin justified before any run:** the seed-to-seed spread of the accepted settings was 0.56 bikes/h (stdev 0.18), in `reports/evidence/lab7-seed-variation.json`. The 2.0 bikes/h margin is more than 3× that spread.
- **Runs after the policy:** the official runs happened on 2026-11-07 between 14:44 and 14:46 UTC, from a clean checkout of `main` at `fb9ebe3`.
- **Entry point:** `uv run --locked python -m bike_demand.pipeline --candidate configs/candidates/<name>.yaml`, after `uv run --locked python -m bike_demand.promote fetch`. Documented in the root README, "Pipeline and gate".

### Decisions

Records are in `bike-demand/decisions/` and the raw run logs in `reports/evidence/lab7-run-*.txt`. All values are validation MAE in bikes/hour on the same 4,358 rows. The naive train-mean baseline scores 154.23.

| Candidate | Settings | Candidate MAE | Accepted MAE | Peak MAE (cand. / acc.) | Bundle | p95 ms | Outcome | Failed rule(s) |
|---|---|---|---|---|---|---|---|---|
| same-as-accepted | 50 trees, depth 10 | 86.85 | 86.85 | 161.20 / 161.20 | 5.2 MB | 12.5 | rejected | `improves_on_accepted` |
| shallow | 20 trees, depth 6 | 90.92 | 86.85 | 173.85 / 161.20 | 0.2 MB | 7.6 | rejected | `improves_on_accepted`, `peak_hours_no_regression` |
| deeper | 100 trees, depth 20, leaf 2 | 86.22 | 86.85 | 157.59 / 161.20 | 33.1 MB | 43.1 | rejected | `improves_on_accepted` |

**Reading the results:**

- `same-as-accepted` reproduces the accepted model exactly (identical MAE), which confirms the comparison is fair: same rows, same labels, same process.
- `deeper` is better by 0.62 bikes/h. That is close to the seed spread (0.56), so the policy does not treat it as a real improvement. It is also 6× larger and 3.5× slower.

### Rejection preserves state (slide 14)

`reports/evidence/lab7-reject-before-after.txt` records three things before and after the official runs:

- the SHA-256 of `registry/accepted.json`;
- the Cloud Run revision serving 100% of traffic;
- the live identity check: model, model digest and commit.

All three are identical: the decision records changed, the accepted bundle and the served model did not.

### Accepted-state boundary

- **Storage:** model binaries are no longer in Git. Accepted bundles live in `gs://mlops-fri2-teama-bike-demand-models/bundles/<version>/`, uploaded without overwrite to a versioned bucket.
- **Pointer:** `bike-demand/registry/accepted.json` is the reviewed pointer.
- **Promotion:** only `bike_demand.promote` writes the bucket and the pointer. It accepts only an `eligible` decision on the exact evaluated bytes, and refuses if the incumbent changed.
- **Cloud Build:** it fetches the bundle named by the pointer and stops unless both digests match.

### Review challenge (slide 17)

Alexandre reviewed PR #43, the gate.

- **Prediction:** an accepted bundle whose bytes were altered must not be loaded.
- **Method:** one byte was appended to a copy of the accepted model.
- **Observed:** `blocked`, exit 2, `integrity.incumbent_bytes: fail`, no score computed.
- **Evidence:** `reports/evidence/lab7-challenge.txt`.

### Who did what

| PR | Author | Content | Review record |
|---|---|---|---|
| #41 | Nicolas (lead) | gate policy, candidates, margin evidence, README section | merged by Thaddée; review comment, no formal approval |
| #40 | Thaddée | `candidate.py` (isolated training, settings guard) + tests | merged by Alban; no formal review recorded |
| #43 | Alban | `gate.py`, `pipeline.py` + tests | Alexandre: changes requested, challenge, approved |
| #44 | Alexandre | bucket store, `accepted.json`, `promote.py`, Cloud Build fetch | merged by Alban; no formal review recorded |
| #45, #46 | Alexandre | Cloud Build fetch repair (red → green), image identity check | approved by Alban |

- **README answers:** Alban's "Failure and decisions" answers were written by Alexandre because Alban was unavailable (stated in the README).
- **Official runs:** Nicolas was unavailable, so Alexandre ran them.

### Limits and handoff to Lab 8

- **Handoff:** only one accepted model version exists, because nothing qualified. The Lab 8 rollback target is therefore a retained, verified Cloud Run revision serving that same accepted bundle, not a previous model version. We report this as a partial handoff (slide 20).
- **Latency:** p95 latency is measured on a laptop, not under Cloud Run load.
- **Validation window:** a single validation half-year was used, and the gate cannot know performance on later data.

## Lab 8 — Service monitoring, incident diagnosis and rollback verification

*Section written by the recorder (Thaddée) after the drill; see `reports/lab8-incident.md`.*
