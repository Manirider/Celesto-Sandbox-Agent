import concurrent.futures
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.config import settings
from app.sandbox.provider import get_provider, CelestoPaymentRequiredError, SandboxProviderError

def run_single_job(job_id: int, sandbox_name: str, provider) -> dict:
    t_start = datetime.now(timezone.utc).isoformat()
    record = {
        "job_id": job_id,
        "sandbox_name": sandbox_name,
        "started_at": t_start,
        "ended_at": None,
        "success": False,
        "cleanup_ok": False,
        "error": None
    }
    handle = None
    try:
        handle = provider.create_sandbox(sandbox_name)
        provider.wait_ready(handle)
        res = provider.execute_command(handle, f"echo 'concurrent_job_{job_id}'")
        record["success"] = (res.get("exit_code") == 0)
    except Exception as e:
        record["error"] = str(e)
    finally:
        if handle:
            try:
                record["cleanup_ok"] = provider.cleanup(handle)
            except Exception:
                record["cleanup_ok"] = False
        record["ended_at"] = datetime.now(timezone.utc).isoformat()
    return record

def main():
    print("=" * 60)
    print("FIVE-JOB CONCURRENCY TEST RUNNER")
    print("=" * 60)

    api_key = os.getenv("CELESTO_API_KEY") or settings.celesto_api_key
    evidence_dir = Path(root_dir) / "reports" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "concurrency_test.log"

    if not api_key:
        print("BLOCKED: CELESTO_API_KEY not configured.")
        sys.exit(1)

    provider = get_provider()
    
    # Generate 5 unique sandbox names adhering to ^sbx-[a-z0-9]{8,}$
    base_epoch = int(time.time())
    jobs_info = [
        (i, f"sbx-c{base_epoch % 1000000:06d}{i:02d}")
        for i in range(1, 6)
    ]

    print("Planned concurrent sandboxes:")
    for jid, sname in jobs_info:
        print(f"  Job {jid}: {sname}")

    print("\nLaunching 5 jobs concurrently with ThreadPoolExecutor...")
    results = []
    t_start_all = time.time()
    payment_error = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(run_single_job, jid, sname, provider): (jid, sname)
            for jid, sname in jobs_info
        }
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            results.append(res)
            if res.get("error") and ("402" in res["error"] or "Payment Required" in res["error"]):
                payment_error = True

    duration = time.time() - t_start_all
    print(f"All 5 jobs completed in {duration:.2f}s")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n--- Concurrency Test Run at {time.strftime('%Y-%m-%dT%H:%M:%SZ')} ---\n")
        f.write(json.dumps(results, indent=2) + "\n")

    if payment_error:
        print("BLOCKED: Real concurrent creation blocked by Celesto Cloud HTTP 402 Payment Required.")
        sys.exit(1)

    all_success = all(r["success"] for r in results)
    all_cleaned = all(r["cleanup_ok"] for r in results)

    # Update reports/concurrency.json with real results
    conc_data = {
        "jobs": [
            {
                "job_id": r["job_id"],
                "sandbox_name": r["sandbox_name"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
                "status": "succeeded" if r["success"] else "failed",
                "cleanup_ok": r["cleanup_ok"]
            }
            for r in results
        ],
        "breakage_notes": "None" if all_success else "Some concurrent jobs encountered errors. See logs."
    }
    with open(Path(root_dir) / "reports" / "concurrency.json", "w", encoding="utf-8") as f:
        json.dump(conc_data, f, indent=2)

    if all_success and all_cleaned:
        print("Concurrency Test: PASS (5/5 succeeded and cleaned up)")
        sys.exit(0)
    else:
        print("Concurrency Test: PARTIAL OR FAILED. Check evidence log.")
        sys.exit(1)

if __name__ == "__main__":
    main()
