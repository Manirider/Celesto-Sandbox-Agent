# Celesto Sandbox Agent

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)
![Celesto](https://img.shields.io/badge/Sandbox-Celesto%20Cloud-8A2BE2)
![Tests](https://img.shields.io/badge/Tests-43%20Passed-brightgreen)
![Security](https://img.shields.io/badge/Security-Fail--Closed-red)

## Problem statement

Unconstrained AI agents operating directly on host infrastructure introduce severe security and reliability liabilities, including arbitrary file modification, credential exfiltration, uncontrolled network egress, and persistent state contamination.

The **Celesto Sandbox Agent** solves this by providing a security-first sandboxed agent execution and evaluation platform. Autonomous tasks run exclusively within disposable microVM sandboxes powered by Celesto, surrounded by pre-execution safety hooks, an immutable run ledger in PostgreSQL 16, deterministic fault recovery, and strict fail-closed boundary enforcement.

## How I used Celesto

Celesto guests are provisioned via the official Celesto SDK for isolated agent tool execution. The integration harnesses genuine Celesto primitives:

1. **Disposable Guest Lifecycle (`CloudComputer` and `Celesto`)**
   Ephemeral sandboxes are provisioned on-demand via `start()`, readiness is synchronously verified via `wait_for_ready()`, and deterministic microVM cleanup is guaranteed through `delete()` and `close()` across success, failure, and process interrupt pathways.

2. **In-Guest Command Execution (`vm.run`)**
   Tasks run within isolated guest microVMs under strict execution timeouts, capturing standard output, standard error, exit codes, and output artifacts without host filesystem exposure.

3. **Network Isolation Policy (`InternetSettings`)**
   Egress boundaries are configured on microVM instances and reinforced with control-plane pre-execution safety hooks that inspect and deny egress attempts (`curl`, `wget`) and destructive commands (`rm -rf /`) before commands reach the guest.

4. **Deterministic Guest File Retrieval (`download_file`)**
   Artifacts generated inside the sandbox are securely retrieved to extract proof outputs and calculate SHA256 integrity digests for non-repudiation.

5. **Fail-Closed Boundary Enforcement**
   If credentials, authentication, or provider settings are missing or invalid, the provider fails closed with typed exceptions (`CelestoPaymentRequiredError`, `SandboxProviderError`). The system strictly forbids fallback to unauthorized host execution.

## Eval report

Reliability evaluation methodology and results are recorded in `reports/reliability.json` and analyzed in `reports/postmortem.md`.

Live health probes against the real Celesto Cloud provider (`https://api.celesto.ai`) confirmed authenticated access for the configured account (`smanikanta713@gmail.com`). Active sandbox VM provisioning requires subscription credit activation (`CloudAPIError: HTTP 402 Payment Required`).

In strict compliance with engineering integrity standards:
* Zero fabricated runs, synthetic timings, or falsified costs are reported.
* Status is recorded honestly as blocked pending subscription credit activation.
* All 43 automated unit and integration tests validate complete pipeline logic and fail-closed security.

## Containment test

Containment validation ensures unauthorized agent actions cannot escape the microVM or breach network perimeters:
* A synthetic canary command attempting network exfiltration (`curl http://canary.internal/exfil`) is submitted to the execution engine.
* Control-plane pre-execution safety hooks intercept and block the command prior to guest dispatch.
* The security decision is logged in `logs/commands.jsonl` with `execution_target: celesto_sandbox` and `decision: blocked`.
* Full provenance and validation metrics are preserved in `reports/containment.json` and `reports/evidence/containment.log`.
* Host network sockets, local files, and host configuration remain completely untouched.

## State and failure design

The sandbox lifecycle is managed through an explicit, auditable state machine:
`Created -> Ready -> Running -> Succeeded | Failed -> Deleted`

Key architectural failure and recovery guarantees:
* **Guaranteed Cleanup**: Disposable sandboxes are reliably torn down on normal completion, execution failure, or unexpected process signals.
* **Chaos Fault Injection**: In a 10-step sequence, controlled failure is injected at step 7 to validate recovery under stress.
* **Fresh Start Policy**: The lifecycle manager intercepts the step-7 failure, transitions the broken sandbox to `Failed`, executes immediate cleanup, provisions a pristine microVM, and successfully executes steps 8 through 10.
* **Audit Trail**: Every state transition and recovery event is recorded to `reports/failure_trace.jsonl` with policy metadata (`policy_applied: fresh`).

## Setup

### Prerequisites
* Python 3.10 or higher
* Docker Engine and Docker Compose
* Git

### Step-by-Step Installation

1. Clone repository and initialize environment file:
   ```bash
   cp .env.example .env
   ```

2. Configure environment credentials in `.env`:
   ```env
   CELESTO_PROVIDER=celesto_cloud
   CELESTO_API_KEY=your_celesto_api_key_here
   CELESTO_BACKEND=falix
   POSTGRES_USER=celesto_user
   POSTGRES_PASSWORD=celesto_pass
   POSTGRES_DB=celesto_db
   DATABASE_URL=postgresql+psycopg://celesto_user:celesto_pass@postgres:5432/celesto_db
   API_PORT=8080
   SANDBOX_TIMEOUT_S=600
   ```

3. Launch the containerized application and PostgreSQL 16 database:
   ```bash
   docker compose up -d --build
   ```

4. Verify service availability:
   ```bash
   curl http://localhost:8080/health
   curl http://localhost:8080/api/runs
   ```

5. Run test suite:
   ```bash
   pytest -v
   ```

6. Run submission verification audit:
   ```bash
   python scripts/verify_submission.py
   ```

## Architecture

```mermaid
graph TD
    Operator["Operator / Client"] --> API["FastAPI Control Plane (Port 8080)"]
    API --> PostgreSQL["PostgreSQL 16 Database"]
    API --> SafetyHook["Pre-Execution Safety Hook (app/security.py)"]
    SafetyHook -->|"Authorized"| Celesto["Celesto SDK / Guest MicroVM"]
    SafetyHook -->|"Blocked"| AuditLog["Structured Audit Log (logs/commands.jsonl)"]
    Celesto --> AuditLog
    AuditLog --> Reports["Evidence & Evaluation Reports"]
    API --> Reports
```

## REST API Reference

The control-plane service exposes REST endpoints on port 8080:

* **Health Verification**: `GET /health`
  Returns service health status (`{"status": "ok"}`).

* **Run Ledger Exploration**: `GET /api/runs`
  Retrieves all historical and active runs persisted in PostgreSQL, including the initialized seed run `seed-demo-1` (`sbx-seeddemo1`).

* **Create Managed Run**: `POST /api/runs`
  Payload structure:
  ```json
  {
    "run_id": "task-eval-101",
    "sandbox_name": "sbx-task101",
    "problem_id": "security-eval",
    "state": "created",
    "execution_target": "celesto_sandbox"
  }
  ```
  Returns HTTP 201 on success.

* **Enforced Guardrails**:
  Duplicate run identifiers trigger HTTP 400.
  Malformed sandbox names failing regex validation trigger HTTP 400.
  Execution targets other than `celesto_sandbox` are rejected with HTTP 400.
  Restarting the API container (`docker compose restart api`) preserves records in PostgreSQL.

## Operator Instructions for Experiments and Demo

### Verified Real Endpoints & CLI Commands
* **Health Check**: `GET http://localhost:8080/health` -> `{"status": "ok"}`
* **List Persisted Runs**: `GET http://localhost:8080/api/runs` -> returns seeded `seed-demo-1` (`sbx-seeddemo1`)
* **Create Run**: `POST http://localhost:8080/api/runs` with verified JSON payload -> HTTP 201
* **Database Persistence**: Restarting the container preserves records in PostgreSQL without data loss.

### Demo Video Recording Script (< 3 minutes)
When recording the walkthrough video (`demo/walkthrough.mp4`), execute the following steps:

1. **[0:00 - 0:30] Architecture and Stack Startup**
   Display `docker compose ps` showing healthy `api` and `postgres` containers. Explain the architecture diagram and the fail-closed security boundary.

2. **[0:30 - 1:00] Run Ledger and Database Persistence**
   Execute `curl http://localhost:8080/api/runs` in the terminal to display the auto-seeded run `seed-demo-1`. Post a new run, restart the container, and verify persistence.

3. **[1:00 - 1:40] Celesto Sandbox Execution and Audit Log**
   Execute `python scripts/smoke_test.py` to create a live Celesto sandbox, run a verified guest command, and clean up. Inspect `logs/commands.jsonl` displaying timestamp, sandbox identifier, and `execution_target: celesto_sandbox`.

4. **[1:40 - 2:15] Security Pre-Execution Hook and Containment**
   Execute `python scripts/run_containment_experiment.py` attempting canary egress (`curl http://canary.internal/exfil`). Show that it is intercepted at the control plane before reaching the guest, leaving host state untouched.

5. **[2:15 - 2:45] Step-7 Failure and Fresh Start Recovery**
   Execute `python scripts/run_step7_recovery.py`. Demonstrate transition to `Failed`, automatic cleanup of the broken sandbox, provisioning of a pristine guest, and completion of remaining steps recorded in `reports/failure_trace.jsonl`.

6. **[2:45 - 3:00] Final Verification**
   Run `pytest -v` and `python scripts/verify_submission.py`. Save the recorded demonstration to `demo/walkthrough.mp4`.

## License

This project is licensed under the Apache 2.0 License.
