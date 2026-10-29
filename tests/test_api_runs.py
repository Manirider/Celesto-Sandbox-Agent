from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_invalid_sandbox_name():
    payload = {
        "run_id": "test-1",
        "sandbox_name": "bad",
        "problem_id": "p1",
        "state": "created",
        "execution_target": "celesto_sandbox"
    }
    r = client.post("/api/runs", json=payload)
    assert r.status_code == 400

def test_invalid_state():
    payload = {
        "run_id": "test-2",
        "sandbox_name": "sbx-abcdefgh",
        "problem_id": "p1",
        "state": "unknown",
        "execution_target": "celesto_sandbox"
    }
    r = client.post("/api/runs", json=payload)
    assert r.status_code == 400

def test_invalid_execution_target():
    payload = {
        "run_id": "test-3",
        "sandbox_name": "sbx-ijklmnop",
        "problem_id": "p1",
        "state": "created",
        "execution_target": "host"
    }
    r = client.post("/api/runs", json=payload)
    assert r.status_code == 400
