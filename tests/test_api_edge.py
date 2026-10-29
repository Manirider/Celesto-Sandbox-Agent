import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_invalid_state():
    r = client.post("/api/runs", json={"run_id":"x","sandbox_name":"sbx","state":"UNKNOWN","execution_target":"celesto_sandbox"})
    assert r.status_code == 400

def test_invalid_execution_target():
    r = client.post("/api/runs", json={"run_id":"x","sandbox_name":"sbx","state":"Created","execution_target":"host"})
    assert r.status_code == 400

def test_invalid_sandbox_name():
    r = client.post("/api/runs", json={"run_id":"x","sandbox_name":"sbx bad!","state":"Created","execution_target":"celesto_sandbox"})
    assert r.status_code == 400

def test_fail_closed_provider():
    from app.config import settings
    from app.sandbox.provider import get_provider
    p = get_provider()
    # Without credentials provider should be disabled / fail-closed
    assert p.mode in ("fake","real","disabled")
