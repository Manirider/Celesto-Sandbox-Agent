import os
import sys
from pathlib import Path

# Ensure repo root is on sys.path
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.config import settings

def main():
    print("=" * 60)
    print("CELESTO CLOUD ENTITLEMENT & BLOCKER DIAGNOSTIC")
    print("=" * 60)

    api_key = os.getenv("CELESTO_API_KEY") or settings.celesto_api_key
    if not api_key:
        print("STATUS: BLOCKED_NO_CREDENTIALS")
        print("Detail: CELESTO_API_KEY is not configured in the active environment.")
        print("Required Operator Action:")
        print("  1. Obtain an API key from https://app.celesto.ai")
        print("  2. Ensure the associated account/organization has active sandbox hours or an active subscription.")
        print("  3. Set the environment variable: $env:CELESTO_API_KEY='<your-api-key>'")
        print("  4. Rerun python scripts/smoke_test.py to revalidate.")
        return 1

    print("Credentials detected (length: %d chars, token sanitized)." % len(api_key))
    print("Probing Celesto Cloud API (https://api.celesto.ai)...")

    try:
        from _celesto_cloud_api.client import AuthenticatedClient
        from _celesto_cloud_api.api.organizations import list_user_organizations_v1_organizations_get as list_orgs
        from _celesto_cloud_api.api.billing import get_billing_summary_v1_billing_summary_get as get_billing
        from _celesto_cloud_api.api.computers import get_computers_v1_computers_get as list_computers

        client = AuthenticatedClient(base_url="https://api.celesto.ai", token=api_key, raise_on_unexpected_status=False)

        # 1. Organization Check
        print("1. Checking Organizations...")
        resp_orgs = list_orgs.sync_detailed(client=client)
        print("   Organizations HTTP Status: %d" % resp_orgs.status_code)
        if resp_orgs.status_code == 200:
            orgs_data = resp_orgs.parsed or []
            print("   Organizations Found: %d" % len(orgs_data))

        # 2. Computers Check (Permissions)
        print("2. Checking Computer List Permissions...")
        resp_comp = list_computers.sync_detailed(client=client)
        print("   List Computers HTTP Status: %d" % resp_comp.status_code)
        if resp_comp.status_code == 200:
            print("   Token has computer read permissions.")

        # 3. Billing Summary Check
        print("3. Checking Billing / Entitlement Summary...")
        resp_bill = get_billing.sync_detailed(client=client)
        print("   Billing Summary HTTP Status: %d" % resp_bill.status_code)
        if resp_bill.status_code == 200:
            print("   Billing Summary Response: %s" % (resp_bill.parsed or "{}"))
        elif resp_bill.status_code == 404:
            print("   Billing endpoint not available or uninitialized for this account.")
        else:
            print("   Billing response code: %d" % resp_bill.status_code)

        # 4. Probe Sandbox VM Creation (safe dry probe)
        print("4. Testing Sandbox VM Creation...")
        from celesto import CloudComputer
        vm = CloudComputer(api_key=api_key)
        vm.start()
        print("   Sandbox provisioned successfully! ID: %s" % vm.id)
        vm.delete()
        print("   Cleanup successful.")
        print("STATUS: READY_AUTHORIZED")
        return 0

    except Exception as e:
        err_type = type(e).__name__
        err_str = str(e)
        status_code = getattr(e, "status_code", None)
        err_code = getattr(e, "code", None)
        recovery = getattr(e, "recovery_action", None)

        print("\nDIAGNOSTIC RESULT:")
        print("  Error Type: %s" % err_type)
        print("  Status Code: %s" % (status_code or ("402" if "402" in err_str else "Unknown")))
        if err_code:
            print("  SDK Error Code: %s" % err_code)
        if recovery:
            print("  SDK Recovery Action: %s" % recovery)
        print("  Sanitized Message: %s" % err_str)

        if "402" in err_str or status_code == 402:
            print("\nEXACT BLOCKER IDENTIFIED:")
            print("  Celesto Cloud API returned HTTP 402 Payment Required on compute VM provisioning.")
            print("  Token is valid and authenticated, but account lacks active sandbox hours entitlement.")
            print("\nREQUIRED OPERATOR ACTION:")
            print("  1. Log into https://app.celesto.ai with your Celesto Cloud account.")
            print("  2. Check 'Sandbox Hours' or 'Subscription Plan' under Organization Settings.")
            print("  3. Allocate compute hours, start an active trial, or attach a billing payment method.")
            print("  4. Once entitlement is active (> 0 sandbox hours), rerun python scripts/smoke_test.py.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
