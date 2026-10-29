import json
import os
import re
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def load_json(path):
    with open(os.path.join(REPO_ROOT, path), "r", encoding="utf-8") as f:
        return json.load(f)

def test_required_files_exist():
    required = [
        "docker-compose.yml",
        "Dockerfile",
        ".env.example",
        "README.md",
        "seeds/01_runs.sql",
        "reports/problem.json",
        "reports/capabilities.json",
        "reports/lifecycle.json",
        "reports/reliability.json",
        "reports/postmortem.md",
        "reports/containment.json",
        "reports/failure_policy.json",
        "reports/failure_trace.jsonl",
        "reports/concurrency.json",
        "logs/commands.jsonl",
        "tests/test_reports.py",
    ]
    for p in required:
        assert os.path.exists(os.path.join(REPO_ROOT, p)), f"Missing {p}"

def test_problem_report():
    data = load_json("reports/problem.json")
    assert len(data.get("who","")) >= 40
    assert len(data.get("agent_work","")) >= 40
    assert len(data.get("proof_output","")) >= 20
    assert data.get("idea_source") in ("idea_bank","original")

def test_capabilities():
    data = load_json("reports/capabilities.json")
    assert isinstance(data, list) and len(data) >= 2
    for c in data:
        assert "id" in c and "why" in c and len(c["why"]) >= 80
        assert os.path.exists(os.path.join(REPO_ROOT, c["evidence_path"]))

def test_lifecycle():
    data = load_json("reports/lifecycle.json")
    assert data.get("cleanup_on_success") is True
    assert data.get("cleanup_on_failure") is True
    assert data.get("cleanup_on_interrupt") is True

def test_reliability_schema():
    data = load_json("reports/reliability.json")
    assert data["run_count"] >= 0
    assert "runs" in data
    assert "postmortem_path" in data
    # No fabricated runs when blocked
    if data.get("run_count") == 0:
        assert data.get("status") in ("BLOCKED_NO_CREDENTIALS", "BLOCKED_PAYMENT_REQUIRED")
        assert data.get("runs") == []

def test_containment():
    data = load_json("reports/containment.json")
    assert data.get("blocked") is True
    assert data.get("host_untouched") is True
    # Must not claim real experiment without provenance
    assert data.get("status") in ("SIMULATED_NO_CREDENTIALS","BLOCKED_NO_CREDENTIALS")
    assert "provenance" in data

def test_failure_policy():
    data = load_json("reports/failure_policy.json")
    assert data["failed_step"] == 7
    assert data["total_steps"] == 10
    assert len(data["rationale"]) >= 200

def test_concurrency():
    data = load_json("reports/concurrency.json")
    jobs = data.get("jobs", [])
    assert len(jobs) >= 5
    names = [j["sandbox_name"] for j in jobs]
    assert len(set(names)) == len(names)

def test_commands_log():
    path = os.path.join(REPO_ROOT, "logs/commands.jsonl")
    with open(path) as f:
        for line in f:
            entry = json.loads(line)
            assert entry["execution_target"] == "celesto_sandbox"

def test_containment_evidence_paths():
    data = load_json("reports/containment.json")
    for p in data.get("evidence_paths", []):
        assert os.path.exists(os.path.join(REPO_ROOT, p)), f"Missing evidence {p}"

