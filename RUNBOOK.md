# RUNBOOK: Bike Demand service on Cloud Run

For the next operator. Follow the steps in order. Record every command output (or its path) and the UTC time in the incident record.

## Last verified context

| Item | Value |
|---|---|
| Last verified | 2026-11-07 16:50 UTC by Alexandre, after the Lab 8 drill: revision `00030-gew`, code `3cd9499`, model `baseline-f01a22df4c39` (sha256 `fd98ceaf…`), identity PASSED, replay MAE 84.25 (= baseline). Record: [`bike-demand/reports/lab8-incident.md`](bike-demand/reports/lab8-incident.md). |
| Service | Cloud Run `mlops-fri2-teama-bike-demand`, region `europe-west1`, project `mlops-demo-512323`, private (identity token required) |
| URL | `https://mlops-fri2-teama-bike-demand-709271018248.europe-west1.run.app` |
| Accepted model | the version and SHA-256 in [`bike-demand/registry/accepted.json`](bike-demand/registry/accepted.json); bundles in `gs://mlops-fri2-teama-bike-demand-models/bundles/<version>/` |
| Deploys | every merge to `main` runs Cloud Build (`cloudbuild.yaml`); each deploy is a new revision tagged `c-<short sha>` |
| Monitoring | [`bike-demand/scripts/monitor_replay.py`](bike-demand/scripts/monitor_replay.py) (definitions in its docstring and in README "Monitoring") |

All commands are PowerShell, run from the repository root unless stated. Set these once per session:

```powershell
$g = "gcloud.cmd"
$svc = "mlops-fri2-teama-bike-demand"
$url = "https://mlops-fri2-teama-bike-demand-709271018248.europe-west1.run.app"
$where = "--region=europe-west1", "--project=mlops-demo-512323"
$env:BIKE_DEMAND_ID_TOKEN = (& $g auth print-identity-token)
```

When you finish, run `Remove-Item Env:BIKE_DEMAND_ID_TOKEN`. Never paste the token anywhere.

## 1. Symptoms that open an incident

Compare with the baseline replay of the same accepted version.

| Signal | Normal (baseline) | Opens an incident |
|---|---|---|
| `/health` | 200, `status: ok`, identity = `accepted.json` | 503, or any identity mismatch |
| Success rate of eligible attempts | 1.0 | below 1.0 |
| Validation MAE of the replay sample | baseline value (bikes/hour) | more than 1.0 above baseline |
| Invalid probes (hr=24) | all rejected with 422 | any other status |
| Cloud Run request events | no 5xx on `/predict` | any 5xx on `/predict` |

**Why these thresholds:**

- **Deterministic replay:** the replay sends the same rows each time, and the same model and code return byte-identical predictions on Windows and Linux (Lab 6 measurement). Any MAE change larger than rounding therefore means something changed.
- **What 1.0 means:** a 1.0 bikes/hour margin ignores nothing real but stays clear of float noise.
- **Rejections:** an intentional 422 is never a failure.

## 2. First checks, cheapest first

Record each result before moving on.

1. **Identity of what is serving**

   ```powershell
   uv run --project bike-demand python bike-demand/scripts/verify_deployment.py --url $url --expected-model <model_version from accepted.json> --expected-model-sha256 <model_sha256 from accepted.json> --expected-revision <last commit you verified>
   ```

   - `model_version` / `model_sha256` mismatch: the **model** boundary changed.
   - `code_revision` mismatch: the **code / release** boundary changed.

2. **Which revision has traffic, and since when**

   ```powershell
   & $g run services describe $svc @where --format="yaml(status.traffic)"
   & $g run revisions list --service=$svc @where --format="table(metadata.name,metadata.creationTimestamp,spec.containers[0].image)" --limit=5
   ```

3. **What the service logged** (structured request events, last hour):

   ```powershell
   $f = 'resource.type="cloud_run_revision" AND resource.labels.service_name="mlops-fri2-teama-bike-demand" AND jsonPayload.event="http_request"'
   & $g logging read $f --project=mlops-demo-512323 --freshness=1h --limit=500 --format="table(timestamp,resource.labels.revision_name,jsonPayload.path,jsonPayload.status_code,jsonPayload.latency_ms,jsonPayload.model_version,jsonPayload.code_revision)"
   ```

4. **Behaviour on known inputs** (same definitions as the baseline):

   ```powershell
   cd bike-demand
   uv run --locked python scripts/monitor_replay.py --url $url --out reports/evidence/lab8-<period>
   cd ..
   ```

5. **What changed in the code** between the last verified commit and the one now serving:

   ```powershell
   git fetch origin
   git log --oneline <last verified commit>..<serving code_revision>
   git diff <last verified commit> <serving code_revision> -- bike-demand/src
   ```

## 3. Decide

| Evidence | Likely boundary | Action |
|---|---|---|
| `code_revision` changed after a merge, model identity unchanged, behaviour degraded (5xx or MAE shift) | release (code) | **Roll back** to the last verified revision (section 4), then fix forward on `main` (section 6). |
| `model_sha256` differs from `accepted.json` | model bytes | **Roll back**; never relabel or load an unverified bundle. |
| `/health` 503 on the new revision only | start-up / configuration | **Roll back**, then read that revision's start-up logs. |
| Only 422 increased | client input | No rollback: inform the client team. |
| Nothing matches | unknown | **Escalate** (section 7) and keep collecting evidence. |

State at least two hypotheses, each with:
- its predicted signature;
- the check that tells them apart;
- the actual result.

Keep the rejected ones in the incident record.

## 4. Roll back to a retained compatible revision

**Name the target before switching.** A target is valid only if all of these hold:

- it is a retained revision of this service whose `/health` identity matches `registry/accepted.json` (same `model_version` and `model_sha256`);
- its `code_revision` is a commit on `main` that was verified before the incident (normally the previous deploy);
- it uses the same feature schema (12 ordered features; the API contract is unchanged).

Steps:

1. **Pre-check** of the target, without moving traffic. Every deploy already tags its revision `c-<short sha>`; use that tag's URL (from `status.traffic` in section 2.2), or add a temporary tag if it has none:

   ```powershell
   & $g run services update-traffic $svc @where --update-tags=rollback=<target revision>
   $tagUrl = "https://rollback---" + ((& $g run services describe $svc @where --format="value(status.url)") -replace '^https://', '')
   uv run --project bike-demand python bike-demand/scripts/verify_deployment.py --url $tagUrl --expected-model <...> --expected-model-sha256 <...> --expected-revision <target commit>
   ```

   **Learned in the Lab 8 drill:** a revision without traffic is scaled to zero, so its first request can take more than the script's 10 s timeout and fail with `The read operation timed out`. That is a cold start, not an identity mismatch. Run the same command again, up to three times, before deciding. A `FAIL` on `model_*` or `code_revision` is a real mismatch: never switch to that target.

2. **The one controlled change:**

   ```powershell
   & $g run services update-traffic $svc @where --to-revisions=<target revision>=100
   ```

Never retrain as a recovery action. Never edit `accepted.json` to match a broken service.

## 5. Verify the recovery with fresh evidence

All three checks must agree:

1. **Identity:** rerun the check from section 2.1 with `--expected-revision <target commit>`. It must say `Deployment verification PASSED`.
2. **Behaviour:** rerun the replay (section 2.4) into `reports/evidence/lab8-recovery`. The success rate and MAE must return to the baseline values.
3. **Signals:** rerun the log query (section 2.3) and read only events after the switch time. They must come from the target revision, with no 5xx on `/predict`.

A successful `update-traffic` command alone does not prove recovery.

## 6. Fix forward on `main`

`main` still contains the faulty commit, so the next merge would redeploy it.

- **Fix:** revert it through a reviewed PR (`git revert -m 1 <merge commit>`), ideally with a test that would have caught it.
- **Check:** after the merge, check the new deploy as in section 5.

## 7. Escalate

Escalate if you cannot name a compatible target, if the target fails its check, or if `gcloud` or Cloud Run access is denied.

- **Who:** the team members listed in `bike-demand/reports/week-04-team.md` (operator on duty first, then whoever merged the last PR).
- **What to record:** the failing step, the exact message, the current traffic split, and who acts next.

## Limitations

- The replay covers a fixed sample of validation-period rows (every 20th row of Jan–Jun 2012), not real traffic.
- Latency is measured from the operator's laptop.
- The live identity check needs a person with Cloud Run access; Cloud Build checks the image before deploy but cannot call the private URL.
- The held test period (Jul–Dec 2012) is never used.
