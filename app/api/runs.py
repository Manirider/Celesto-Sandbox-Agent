import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
import os

router = APIRouter(prefix="/api/runs")

from app.config import settings

DATABASE_URL = os.getenv("DATABASE_URL", settings.database_url)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    return _engine

SANDBOX_NAME_RE = re.compile(r"^sbx-[a-z0-9]{8,}$")
ALLOWED_STATES = {"created","ready","running","succeeded","failed","deleted"}

class RunCreate(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str

    @field_validator("sandbox_name")
    @classmethod
    def validate_sandbox(cls, v):
        if not SANDBOX_NAME_RE.match(v):
            raise ValueError("invalid sandbox name")
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v):
        if v not in ALLOWED_STATES:
            raise ValueError("unknown state")
        return v

    @field_validator("execution_target")
    @classmethod
    def validate_target(cls, v):
        if v != "celesto_sandbox":
            raise ValueError("invalid execution target")
        return v

class RunOut(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str

@router.get("", response_model=list[RunOut])
def list_runs():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT run_id, sandbox_name, problem_id, state, execution_target FROM runs ORDER BY id"))
        return [RunOut(run_id=r[0], sandbox_name=r[1], problem_id=r[2], state=r[3], execution_target=r[4]) for r in rows]

@router.post("", status_code=201)
def create_run(payload: RunCreate):
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target) VALUES (:run_id,:sandbox_name,:problem_id,:state,:execution_target)"),
                {
                    "run_id": payload.run_id,
                    "sandbox_name": payload.sandbox_name,
                    "problem_id": payload.problem_id,
                    "state": payload.state,
                    "execution_target": payload.execution_target,
                }
            )
    except IntegrityError:
        raise HTTPException(status_code=400, detail="duplicate run_id or sandbox_name")
    except Exception as e:
        raise HTTPException(status_code=500, detail="database error")
    return {"status": "created"}
