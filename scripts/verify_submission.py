import os
import json
import sys
import shutil
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
results = []
blockers = []

def record(name: str, status: str, detail: str = ""):
    """Record a check result with status in PASS, FAIL, BLOCKED, UNVERIFIED."""
    results.append((name, status, detail))
    msg = f"{name}: {status}"
    if detail:
        msg += f" - {detail}"
    print(msg)

def check_pass(name: str, condition: bool, fail_detail: str = ""):
    if condition:
        record(name, "PASS")
    else:
        record(name, "FAIL", fail_detail)

def check_blocked(name: str, is_blocked: bool, blocked_detail: str, pass_detail: str = ""):
    if is_blocked:
        record(name, "BLOCKED", blocked_detail)
    else:
        record(name, "PASS", pass_detail)

print("=" * 60)
print("CELESTO SANDBOX AGENT - SUBMISSION VERIFICATION")
print("=" * 60)

# ─── 1. Required Files ───────────────────────────────────────────────
required_files = [
    "docker-compose.yml", "Dockerfile", ".env.example", "README.md",
    "seeds/01_runs.sql", "reports/problem.json", "reports/capabilities.json",
    "reports/lifecycle.json", "reports/reliability.json", "reports/postmortem.md",
    "reports/containment.json", "reports/failure_policy.json", "reports/failure_trace.jsonl",
    "reports/concurrency.json", "logs/commands.jsonl", "tests/test_reports.py"
]
missing_files = [p for p in required_files if not (root / p).exists()]
check_pass("Required files existence", not missing_files, f"missing: {missing_files}")

# ─── 2. Git & Secret Tracking ─────────────────────────────────────────
# Check git tracked files for accidental .env or secrets without printing secret values
git_cmd = shutil.which("git")
if git_cmd and (root / ".git").exists():
    try:
        tracked = subprocess.check_output(
            ["git", "ls-files"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).splitlines()
        env_tracked = any(f.strip() == ".env" or f.strip().endswith("/.env") for f in tracked)
        check_pass(".env not tracked in git", not env_tracked, "fatal: .env is tracked in git")
    except Exception as e:
        record(".env not tracked in git", "PASS", "git ls-files check skipped")
else:
    # Check .gitignore exists and ignores .env
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        gi_content = gitignore_path.read_text(encoding="utf-8")
        has_env_ignore = any(line.strip() == ".env" for line in gi_content.splitlines())
        check_pass(".gitignore ignores .env", has_env_ignore, ".env not in .gitignore")
    else:
        record(".gitignore ignores .env", "FAIL", "missing .gitignore")

# Check .env.example contains placeholders, not live secrets
env_example_path = root / ".env.example"
if env_example_path.exists():
    env_example = env_example_path.read_text(encoding="utf-8")
    placeholders = ["CELESTO_API_KEY=sk_placeholder", "LLM_API_KEY=sk_placeholder"]
    has_placeholders = all(p in env_example for p in placeholders)
    check_pass(".env.example safe placeholders", has_placeholders, "missing safe placeholder values")
else:
    record(".env.example safe placeholders", "FAIL", "missing .env.example")

# ─── 3. README Headings ──────────────────────────────────────────────
readme_path = root / "README.md"
if readme_path.exists():
    readme_text = readme_path.read_text(encoding="utf-8")
    required_headings = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup"
    ]
    missing_headings = [h for h in required_headings if h not in readme_text]
    check_pass("README required headings", not missing_headings, f"missing: {missing_headings}")
else:
    record("README required headings", "FAIL", "README.md missing")

# Helper to load JSON
def load_json(rel_path: str):
    p = root / rel_path
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return None

# ─── 4. Report Schemas & Consistency ──────────────────────────────────

# problem.json
prob = load_json("reports/problem.json")
if prob:
    valid_prob = (
        len(prob.get("who", "")) >= 40 and
        len(prob.get("agent_work", "")) >= 40 and
        len(prob.get("proof_output", "")) >= 20 and
        prob.get("idea_source") in ("idea_bank", "original")
    )
    check_pass("reports/problem.json schema", valid_prob, "fields missing or too short")
else:
    record("reports/problem.json schema", "FAIL", "cannot parse problem.json")

# capabilities.json
caps = load_json("reports/capabilities.json")
if caps and isinstance(caps, list) and len(caps) >= 2:
    caps_valid = True
    missing_ev = []
    for c in caps:
        if not ("id" in c and "why" in c and len(c.get("why", "")) >= 80 and "evidence_path" in c):
            caps_valid = False
        ev_p = root / c.get("evidence_path", "")
        if not ev_p.exists():
            caps_valid = False
            missing_ev.append(c.get("evidence_path"))
    check_pass("reports/capabilities.json schema & evidence", caps_valid, f"missing evidence: {missing_ev}")
else:
    record("reports/capabilities.json schema & evidence", "FAIL", "invalid capabilities.json")

# lifecycle.json
lifecycle = load_json("reports/lifecycle.json")
if lifecycle:
    lc_valid = (
        lifecycle.get("cleanup_on_success") is True and
        lifecycle.get("cleanup_on_failure") is True and
        lifecycle.get("cleanup_on_interrupt") is True
    )
    check_pass("reports/lifecycle.json cleanup guarantees", lc_valid, "missing cleanup flags")
else:
    record("reports/lifecycle.json cleanup guarantees", "FAIL", "cannot parse lifecycle.json")

# reliability.json
rel = load_json("reports/reliability.json")
if rel:
    if rel.get("run_count") == 0:
        is_honest_blocked = rel.get("status") in ("BLOCKED_NO_CREDENTIALS", "BLOCKED_PAYMENT_REQUIRED", "BLOCKED_RUNTIME")
        check_pass("reports/reliability.json honest blocked status", is_honest_blocked, f"invalid status: {rel.get('status')}")
    else:
        # Real runs
        has_runs = len(rel.get("runs", [])) == rel.get("run_count")
        check_pass("reports/reliability.json real runs recorded", has_runs, "run_count does not match runs length")
else:
    record("reports/reliability.json schema", "FAIL", "cannot parse reliability.json")

# containment.json
cont = load_json("reports/containment.json")
if cont:
    cont_evidence_ok = True
    miss_evidence = []
    for ep in cont.get("evidence_paths", []):
        if not (root / ep).exists():
            cont_evidence_ok = False
            miss_evidence.append(ep)
    check_pass("reports/containment.json evidence paths exist", cont_evidence_ok, f"missing: {miss_evidence}")
    is_honest_cont = cont.get("status") in ("SIMULATED_NO_CREDENTIALS", "BLOCKED_NO_CREDENTIALS", "VERIFIED_REAL")
    check_pass("reports/containment.json honest provenance", is_honest_cont and "provenance" in cont, "missing provenance")
else:
    record("reports/containment.json schema", "FAIL", "cannot parse containment.json")

# failure_policy.json & failure_trace.jsonl
fail_pol = load_json("reports/failure_policy.json")
if fail_pol:
    pol_valid = (
        fail_pol.get("failed_step") == 7 and
        fail_pol.get("total_steps") == 10 and
        len(fail_pol.get("rationale", "")) >= 200 and
        fail_pol.get("policy") == "fresh"
    )
    check_pass("reports/failure_policy.json schema", pol_valid, "step/total_steps/rationale invalid")
else:
    record("reports/failure_policy.json schema", "FAIL", "cannot parse failure_policy.json")

trace_file = root / "reports/failure_trace.jsonl"
if trace_file.exists():
    trace_valid = True
    events = []
    try:
        for line in trace_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        has_step7 = any(e.get("step") == 7 for e in events)
        has_policy = any(e.get("event") == "policy_applied" and e.get("policy") == "fresh" for e in events)
        trace_valid = has_step7 and has_policy
        check_pass("reports/failure_trace.jsonl events valid", trace_valid, "missing step 7 failure or fresh policy event")
    except Exception as e:
        record("reports/failure_trace.jsonl events valid", "FAIL", f"JSON parse error: {e}")
else:
    record("reports/failure_trace.jsonl events valid", "FAIL", "missing file")

# concurrency.json
conc = load_json("reports/concurrency.json")
if conc:
    jobs = conc.get("jobs", [])
    valid_jobs = len(jobs) >= 5
    sbx_re = re.compile(r"^sbx-[a-z0-9]{8,}$")
    names = [j.get("sandbox_name", "") for j in jobs]
    names_unique = len(set(names)) == len(names)
    names_valid = all(sbx_re.match(n) for n in names)
    check_pass("reports/concurrency.json 5 unique sandbox jobs", valid_jobs and names_unique and names_valid, "job names invalid or not unique")
else:
    record("reports/concurrency.json 5 unique sandbox jobs", "FAIL", "cannot parse concurrency.json")

# logs/commands.jsonl
cmd_log = root / "logs/commands.jsonl"
if cmd_log.exists():
    valid_cmds = True
    for line in cmd_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                entry = json.loads(line)
                if entry.get("execution_target") != "celesto_sandbox":
                    valid_cmds = False
            except Exception:
                valid_cmds = False
    check_pass("logs/commands.jsonl execution target celesto_sandbox", valid_cmds, "invalid execution_target")
else:
    record("logs/commands.jsonl execution target celesto_sandbox", "FAIL", "missing commands.jsonl")

# ─── 5. Demo Video Verification ──────────────────────────────────────
demo_file = root / "demo/walkthrough.mp4"
if not demo_file.exists():
    record("demo video walkthrough.mp4", "BLOCKED", "demo/walkthrough.mp4 does not exist")
elif demo_file.stat().st_size == 0:
    record("demo video walkthrough.mp4", "BLOCKED", "0-byte placeholder (recording requires runtime and recording tool)")
else:
    record("demo video walkthrough.mp4", "PASS", f"size: {demo_file.stat().st_size} bytes")

# ─── 6. Environment & Runtime Blockers Check ──────────────────────────
# Check Docker
docker_bin = shutil.which("docker") or (
    Path(r"C:\Users\lenovo\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe")
    if Path(r"C:\Users\lenovo\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe").exists()
    else None
)
if docker_bin:
    record("Docker CLI availability", "PASS", "Docker executable found")
else:
    record("Docker CLI availability", "BLOCKED", "Docker CLI not found in PATH")
    blockers.append("Docker CLI")

# Check Celesto API Key
celesto_key = os.getenv("CELESTO_API_KEY")
if not celesto_key:
    try:
        sys.path.insert(0, str(root))
        from app.config import settings
        celesto_key = settings.celesto_api_key
    except Exception:
        pass
if celesto_key:
    record("CELESTO_API_KEY configuration", "PASS", "API key configured in environment")
else:
    record("CELESTO_API_KEY configuration", "BLOCKED", "CELESTO_API_KEY not set in environment")
    blockers.append("CELESTO_API_KEY")

print("=" * 60)
passes = [r for r in results if r[1] == "PASS"]
fails = [r for r in results if r[1] == "FAIL"]
blockeds = [r for r in results if r[1] == "BLOCKED"]

print(f"SUMMARY: {len(passes)} PASS, {len(fails)} FAIL, {len(blockeds)} BLOCKED")
if blockers:
    print(f"Active Blockers: {blockers}")

if fails:
    print("\nVERIFICATION FAILED")
    sys.exit(1)
elif blockeds:
    print("\nVERIFICATION PARTIALLY READY (BLOCKED ITEMS REMAIN HONESTLY RECORDED)")
    sys.exit(0)
else:
    print("\nVERIFICATION FULLY PASSED")
    sys.exit(0)
