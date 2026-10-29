import json
import os
import sys
import time
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.config import settings
from app.sandbox.provider import get_provider, CelestoPaymentRequiredError, SandboxProviderError
from app.lifecycle import SandboxLifecycle

def main():
    print("=" * 60)
    print("STEP-7 FAILURE & FRESH RECOVERY EXPERIMENT RUNNER")
    print("=" * 60)

    api_key = os.getenv("CELESTO_API_KEY") or settings.celesto_api_key
    if not api_key:
        print("BLOCKED: CELESTO_API_KEY not configured.")
        sys.exit(1)

    provider = get_provider()
    steps = [f"echo step_{i}" for i in range(1, 11)]
    sbx_initial = f"sbx-recov{int(time.time()) % 1000000:06d}"
    sbx_fresh = f"sbx-fresh{int(time.time()) % 1000000:06d}"

    print(f"Initial Sandbox: {sbx_initial}")
    print(f"Target Failure Step: 7 of 10")
    print(f"Fresh Recovery Sandbox: {sbx_fresh}")

    lc = SandboxLifecycle(sbx_initial, provider=provider)
    try:
        print("Starting 10-step lifecycle with failure injected at step 7...")
        lc.run(steps, inject_failure_at=7)
        print("FAIL: Step 7 failure was not observed!")
        sys.exit(1)

    except RuntimeError as re:
        print(f"PASS: Injected failure observed at step 7: {re}")
        assert lc.state == "Failed"

        # Apply fresh recovery policy
        print("Applying 'fresh' recovery policy...")
        try:
            recovery_result = lc.recover_fresh(steps, sbx_fresh)
            print(f"Fresh recovery completed successfully: {recovery_result}")
            assert recovery_result["state"] == "Succeeded"
            print("Step-7 Failure & Recovery Experiment: PASS")
            sys.exit(0)
        except CelestoPaymentRequiredError as cpe:
            print(f"BLOCKED: Fresh sandbox creation blocked by HTTP 402: {cpe}")
            sys.exit(1)
        except Exception as e:
            print(f"FAILED during recovery: [{type(e).__name__}] {e}")
            sys.exit(1)

    except CelestoPaymentRequiredError as cpe:
        print(f"BLOCKED: Celesto Cloud returned HTTP 402 Payment Required: {cpe}")
        sys.exit(1)
    except Exception as e:
        print(f"BLOCKED/FAILED during initialization: [{type(e).__name__}] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
