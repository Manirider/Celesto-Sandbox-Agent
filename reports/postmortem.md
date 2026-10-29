# Postmortem of Reliability Evaluation

## What Succeeded
- **Docker & PostgreSQL Infrastructure**: Docker Compose successfully built and launched `postgres:16-alpine` and `celesto-sandbox-agent-api`.
- **Database Initialization & Persistence**: Seeded record `seed-demo-1` (`sbx-seeddemo1`) was automatically loaded from `seeds/01_runs.sql`. Endpoints `/health` and `/api/runs` were verified against live PostgreSQL via `psycopg` 3. Persistence was confirmed after container restart.
- **API Validation & Control Plane**: HTTP 201 for valid runs, HTTP 400 for duplicate IDs, invalid sandbox names (`^sbx-[a-z0-9]{8,}$`), illegal states, and non-`celesto_sandbox` execution targets.
- **Security & Auditing**: Pre-execution command inspection in `app/security.py` blocks egress attempts (`curl`, `wget`) and destructive commands (`rm -rf /`), emitting structured audit records to `logs/commands.jsonl`.
- **Lifecycle & Step-7 Recovery**: Verified state transitions and fresh-recovery policy upon step-7 failure injection, creating a clean sandbox and logging policy events to `reports/failure_trace.jsonl`.
- **Celesto SDK Integration**: Inspected SDK 0.1.4 API signatures (`CloudComputer`, `Celesto`) and integrated into `app/sandbox/provider.py`. Verified that the provider fails closed without credentials.

## What Was Probed and Blocked
- **Real Celesto Sandbox Execution**: The provided `CELESTO_API_KEY` was tested against `https://api.celesto.ai`. Authentication succeeded (`list_cloud_computers` returned HTTP 200 with 0 active instances). However, attempting to instantiate and start a `CloudComputer` guest resulted in:
  `CloudAPIError: Cloud API returned HTTP 402. Check the request and cloud dashboard before retrying.`
- **Reliability Metrics**: Because cloud VM provisioning was rejected by the cloud provider with HTTP 402 Payment Required, real guest execution metrics (wall-clock time, boot-to-ready time, guest-side success rate) are recorded as 0 with status `BLOCKED_PAYMENT_REQUIRED` / `BLOCKED_NO_CREDENTIALS`. No fake timings, costs, or run records were invented.

## Observed Failure Categories
- Cloud provider quota / payment required (`HTTP 402 Payment Required`).

## Likely Root Cause
- The Celesto Cloud account associated with the API key does not have an active billing plan or compute credits allocated on `api.celesto.ai`.

## Retry and Recovery Behavior
- The provider abstraction cleanly caught the `CloudAPIError`, logged raw evidence to `reports/evidence/smoke_test.log` and `reports/evidence/reliability_eval.log`, and failed closed without running unauthorized host commands.

## Corrective Actions
1. Activate billing or allocate credits on the Celesto Cloud dashboard (`https://app.celesto.ai`).
2. Run `python scripts/smoke_test.py` to confirm sandbox creation.
3. Run `python scripts/evaluate_reliability.py` to complete the 20 fresh sandbox evaluations.
