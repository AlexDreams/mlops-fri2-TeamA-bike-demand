# Lab 8 incident record: Bike Demand on Cloud Run

All times are UTC on 2026-11-07. Every value below comes from a raw file in [`evidence/`](evidence/); nothing in those files was edited.

## 1. Roles and scope

| Role | Member | What they did |
|---|---|---|
| Operator | Alexandre | Measured the baseline, noticed the signal, tested hypotheses, rolled back and verified, without being told the fault. |
| Injector | Alban | Chose and shipped the fault through PR #49. He was then unavailable, so his injection note was not received (section 9). |
| Recorder | Thaddée | Approved and merged the fault PR without informing the operator; opened the revert PR #50; reviewed this record. This record was drafted from the raw evidence by the operator, after the diagnosis, and reviewed by the recorder. |

**Scope:**

- **Service:** our own service `mlops-fri2-teama-bike-demand` (europe-west1, project `mlops-demo-512323`) only.
- **Accepted bundle:** `baseline-f01a22df4c39`, sha256 `fd98ceaf…` (`registry/accepted.json`), unchanged throughout.

## 2. Baseline: normal before the incident

| Item | Value |
|---|---|
| Workload | `scripts/monitor_replay.py`: 218 validation rows (every 20th, Jan–Jun 2012) + 10 invalid probes (`hr = 24`) |
| Window | 15:33:59 – 15:34:19 |
| Serving identity | revision `00025-cow`, `code_revision 713b00d`, model `baseline-f01a22df4c39`, sha256 `fd98ceaf…` (`Deployment verification PASSED`) |
| Eligible / good | 218 / 218 (success rate 1.0) |
| Validation MAE | 84.25 bikes/h (mean prediction 131.83) |
| Latency p50 / p95 (laptop to Cloud Run) | 84 / 117 ms |
| Probes rejected with 422 | 10/10 |
| Raw evidence | [`lab8-baseline/`](evidence/lab8-baseline/), [`lab8-baseline-identity.txt`](evidence/lab8-baseline-identity.txt), [`lab8-baseline-traffic.txt`](evidence/lab8-baseline-traffic.txt) |

## 3. Timeline

| Time | Who | What happened / was observed | Evidence |
|---|---|---|---|
| 15:34:19 | Operator | Baseline replay finished; identity PASSED | `lab8-baseline/summary.json` |
| 15:56:46 | Recorder | PR #49 (author Alban, title "Normalise request hour before prediction") approved and merged; operator not informed | GitHub PR #49 |
| 15:56:50 – 16:03:51 | Cloud Build | Build `a22da9e3` for `8be8346`: tests, image identity check and deploy all green; traffic moved to revision `00027-nep` | Cloud Build history |
| 16:05:25 | Operator | **First signal** (watch run 1): MAE 95.14 instead of 84.25 | `lab8-watch-log.txt`, `lab8-watch-1/` |
| 16:05 | Operator | Hypotheses A, B and C written down before any check (section 5) | team chat |
| 16:07:08 | Operator | Identity check: model and digest match `accepted.json`; `code_revision` 8be8346 ≠ 713b00d | `lab8-diag-identity.txt` |
| 16:07 | Operator | Traffic: 100% on `00027-nep` (tag `c-8be8346`); Cloud Run events for `/predict`: only 200 and 422, no 5xx | `lab8-diag-traffic.txt`, `lab8-diag-logs-status.txt` |
| 16:07:19 | Operator | Code change between 713b00d and 8be8346: one edit in `api.py`, `values["hr"] = (values["hr"] + 1) % 24` | `lab8-diag-gitlog.txt`, `lab8-diag-code-diff.txt` |
| 16:08:30 | Operator | Rollback target `00025-cow` named; pre-check through its tag URL **timed out** (revision scaled to zero, cold start > 10 s) | `lab8-rollback-target-check.txt` |
| 16:08:30 | Operator | Traffic switched: 100% to `00025-cow` | `lab8-rollback-action.txt` |
| 16:08:56 – 16:09:15 | Operator | Recovery replay: MAE 84.25, success 1.0; identity PASSED | `lab8-recovery/`, `lab8-recovery-identity.txt` |
| 16:09 | Operator | Cloud Run events in the last 10 minutes show `00025-cow` serving `/predict` again | `lab8-recovery-logs-status.txt` |
| 16:37:40 | Recorder / Operator | Revert PR #50 (author Thaddée) approved and merged by Alexandre; `main` no longer contains the fault | GitHub PR #50 |

**Exposure:** the faulty revision served all traffic from about 16:03:51 (end of its deploy) to 16:08:30, about 4.7 minutes. Detection took 1.6 minutes after the deploy, and recovery took 3.1 minutes after the first signal.

## 4. First signal

| Item | Value |
|---|---|
| Observed signal | Validation MAE on the replay sample **95.14 bikes/h**, +10.89 over the 84.25 baseline (threshold: more than 1.0 above baseline) |
| Time | 16:05:25 (replay window 16:05:06 – 16:05:25) |
| Affected scope | All 218 eligible requests answered 200 with valid-looking predictions; success rate 1.0; `/health` 200. A silent quality change, not an outage. |
| Version observed | revision `00027-nep`, `code_revision 8be8346`, model `baseline-f01a22df4c39`, sha256 `fd98ceaf…` |
| Raw evidence | `lab8-watch-1/events.jsonl` (218 predictions), `lab8-watch-1/summary.json`, `lab8-watch-log.txt` |
| Interpretation at that time | Something changed the predictions for identical inputs, without errors. Cause unknown. |

## 5. Hypotheses

Each predicted signature was written before its check was run.

| | Hypothesis | Predicted signature | Discriminating check | Actual result | Status |
|---|---|---|---|---|---|
| A | The served model bytes changed | `model_sha256` ≠ `fd98ceaf…` | `/health` identity against `accepted.json` | `model_version` OK, `model_sha256` OK | **rejected** |
| B | A code release changed request handling | model identical, `code_revision` changed, same inputs give different predictions | identity (`code_revision`), revision list, `git diff 713b00d 8be8346 -- bike-demand/src` | `code_revision` 8be8346 (FAIL vs 713b00d); diff shifts `hr` by +1 before prediction | **supported** |
| C | Platform or network problem | 5xx or latency spike on all paths | Cloud Run request events by revision and status; replay latency | only 200 and 422; p95 108 ms vs 117 ms at baseline | **rejected** |

**Why B explains the symptom:** the hour is the model's strongest feature. Predicting every request for the next hour keeps the outputs plausible (no error, mean prediction 129.28 vs 131.83) but wrong for the requested hour, which raises the MAE.

**Still uncertain:** we did not measure which hours were affected most; the replay sample is 218 rows, not real traffic.

## 6. Boundaries checked

| Boundary | Baseline | During incident | Changed? | Explains the symptom? |
|---|---|---|---|---|
| Service revision and image | `00025-cow`, image `…:713b00d…` | `00027-nep`, image `…:8be8346…` | yes | yes, it carries the code change |
| Model version and verified bytes | `baseline-f01a22df4c39`, `fd98ceaf…` | same | no | no |
| Configuration and schema | 12 ordered features, same API contract | same (requests still validated, 422 on `hr = 24`) | no | no |
| Inputs (replay population) | same 218 rows | same 218 rows | no | no |

**Not checked:** Cloud Run environment variables of `00027-nep` (not needed once the diff explained the symptom); real user traffic (none in this drill).

## 7. Decision and rollback target

- **Why rollback fits:** the fault is a release fault (code), the accepted model is intact, and a retained revision runs the last verified code with that model. Switching traffic is one reversible change; no retraining.
- **Target:** revision `00025-cow` (tag `c-713b00d`).
  - **Accepted decision record:** the Lab 4 baseline, retained after the Lab 7 gate rejected all three candidates (`decisions/`).
  - **Model:** `baseline-f01a22df4c39`, sha256 `fd98ceaf…`; matches `accepted.json`.
  - **Code and dependencies:** commit `713b00d` (main, verified PASSED at the 15:34 baseline), same `uv.lock`.
  - **Feature schema and configuration:** 12 ordered features, unchanged API contract.
- **Action at 16:08:30:** `gcloud run services update-traffic mlops-fri2-teama-bike-demand --to-revisions=mlops-fri2-teama-bike-demand-00025-cow=100 --region=europe-west1`.
- **Pre-check:** the identity check through the tag URL timed out. The revision had no traffic and was scaled to zero, so its cold start exceeded the 10 s client timeout. We switched on the strength of the same revision's PASSED check at 15:34 and verified right after (section 8). RUNBOOK revised: retry the pre-check after a timeout.
- **What could still fail:** `main` still contained the fault until PR #50 (16:37), so any merge in between would have redeployed it.

## 8. Verification after recovery

| Source | Expected (retained) | Observed (fresh, after 16:08:30) | Agrees? |
|---|---|---|---|
| Identity (`verify_deployment.py`) | `baseline-f01a22df4c39`, `fd98ceaf…`, `713b00d` | all OK, `Deployment verification PASSED` | yes |
| Behaviour (replay, live URL) | success 1.0, MAE 84.25 | success 1.0, MAE 84.25 (identical to the baseline), 422 on 10/10 | yes |
| Signals (Cloud Run events, last 10 min) | `/predict` served by `00025-cow`, no 5xx | `00025-cow`: 200s only; earlier `00027-nep` events are from before the switch | yes |

Observation window: 16:08:56 – 16:09:15 (replay) and 10 minutes of Cloud Run events. Raw: [`lab8-recovery/`](evidence/lab8-recovery/), [`lab8-recovery-identity.txt`](evidence/lab8-recovery-identity.txt), [`lab8-recovery-logs-status.txt`](evidence/lab8-recovery-logs-status.txt).

## 9. Fault revealed

- **Injection note:** Alban's note was not received because he was unavailable after injecting.
- **What the fault was:** per PR #49 (author Alban, merged 15:56:46 by Thaddée), `bike-demand/src/bike_demand/api.py`, function `predict`, built the prediction row with `values["hr"] = (values["hr"] + 1) % 24`.
- **Why it passed CI:** the API tests use a fake model that ignores its input values. It also passed Cloud Build's image identity check, because `/health` was correct.
- **Diagnosis vs actual fault:** matched. Hypothesis B identified the exact line, from the code diff, after A and C were rejected by evidence.

## 10. Baseline vs incident vs recovery

Same definitions in the three periods (README "Monitoring").

| Period | Window | Revision / code / model | Eligible | Good | Success rate | MAE (bikes/h) | p95 ms | 422 probes | 5xx |
|---|---|---|---|---|---|---|---|---|---|
| Baseline | 15:33:59 – 15:34:19 | `00025-cow` / `713b00d` / `fd98ceaf…` | 218 | 218 | 1.0 | 84.25 | 117 | 10/10 | 0 |
| Incident | 16:05:06 – 16:05:25 | `00027-nep` / `8be8346` / `fd98ceaf…` | 218 | 218 | 1.0 | 95.14 | 109 | 10/10 | 0 |
| After rollback | 16:08:56 – 16:09:15 | `00025-cow` / `713b00d` / `fd98ceaf…` | 218 | 218 | 1.0 | 84.25 | 108 | 10/10 | 0 |

- **What improved:** MAE back to exactly the baseline value; identity matches the retained expectation.
- **What remains unknown:** behaviour on real traffic; which hours were most affected.
- **What would falsify the recovery claim:** a replay MAE away from 84.25 on the same rows, any `/predict` event from `00027-nep` after 16:08:30, or an identity mismatch.

## 11. Observed, unknown, next

- **Observed:** a silent, CI-passing code release degraded prediction quality by 10.9 bikes/h; the replay monitor caught it on its first run; rollback to a retained revision restored the exact baseline.
- **Unknown:** how quickly real-traffic metrics alone (without labels) would have shown it.
- **Next actions:**
  - **Revert on `main`:** done in PR #50, owner Thaddée.
  - **Guard test:** `test_request_values_reach_the_model_unchanged` fails 5/5 on the faulty code (`lab8-guard-red-on-fault.txt`). Owner Alexandre, final Lab 8 PR.
- **Blockers:** the injector and the recorder were partly unavailable; roles were covered as described in section 1.
- **Local vs remote:** the replay, identity checks and rollback ran from the operator's laptop against Cloud Run; CI and Cloud Build ran remotely.
- **Health vs predictive quality:** `/health`, success rate and logs stayed normal; only the quality signal (MAE on labelled replay rows) detected the incident.
