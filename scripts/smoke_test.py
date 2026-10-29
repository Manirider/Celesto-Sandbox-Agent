import os
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.config import settings

def main():
    print("Checking Celesto configuration...")
    api_key = os.getenv("CELESTO_API_KEY") or settings.celesto_api_key
    provider_name = os.getenv("CELESTO_PROVIDER") or settings.celesto_provider or "celesto_cloud"

    if not api_key:
        print("BLOCKED: CELESTO_API_KEY not set in environment or config")
        sys.exit(1)

    print("Credentials present. Verifying Celesto provider...")
    t0 = time.time()
    evidence_dir = Path(__file__).resolve().parent.parent / "reports" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    log_file = evidence_dir / "smoke_test.log"

    try:
        from celesto import CloudComputer
        print("Initializing Celesto CloudComputer sandbox...")
        computer = CloudComputer(api_key=api_key)
        print("Starting sandbox guest...")
        computer.start()
        boot_time = time.time() - t0
        print(f"Sandbox started (boot time: {boot_time:.2f}s, ID: {computer.id})")

        print("Executing command: echo celesto-smoke-verified...")
        t_cmd = time.time()
        res = computer.run("echo celesto-smoke-verified", timeout=30)
        cmd_time = time.time() - t_cmd
        print(f"Command completed in {cmd_time:.2f}s: {res.output.strip()} (ok: {res.ok})")

        print("Cleaning up sandbox...")
        computer.delete()
        print("Cleanup successful!")

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} Celesto smoke test PASSED: id={computer.id}, boot={boot_time:.2f}s\n")
        print("Smoke test PASSED!")
        sys.exit(0)

    except Exception as e:
        err_msg = str(e)
        err_type = type(e).__name__
        print(f"Celesto smoke test BLOCKED/FAILED: [{err_type}] {err_msg}")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} Celesto smoke test FAILED/BLOCKED: [{err_type}] {err_msg}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
