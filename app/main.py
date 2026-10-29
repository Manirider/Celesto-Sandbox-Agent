from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.api import runs, health


def init_db():
    """Idempotently initialize database tables and seed record if database is reachable."""
    try:
        from app.api.runs import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS runs (
                    id SERIAL PRIMARY KEY,
                    run_id VARCHAR(255) UNIQUE NOT NULL,
                    sandbox_name VARCHAR(255) NOT NULL,
                    problem_id VARCHAR(255) NOT NULL,
                    state VARCHAR(50) NOT NULL CHECK (state IN ('created','ready','running','succeeded','failed','deleted')),
                    execution_target VARCHAR(100) NOT NULL CHECK (execution_target = 'celesto_sandbox'),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_sandbox_name ON runs(sandbox_name);
                INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
                VALUES ('seed-demo-1', 'sbx-seeddemo1', 'demo-problem', 'deleted', 'celesto_sandbox')
                ON CONFLICT (run_id) DO NOTHING;
            """))
    except Exception:
        # Gracefully proceed if DB is not yet online during test or startup
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Celesto Sandbox Control Plane", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": "invalid request"},
    )


app.include_router(health.router)
app.include_router(runs.router)


@app.get("/")
def root():
    return {
        "message": "Celesto Sandbox Agent Control Plane",
        "docs_url": "/docs",
        "health_url": "/health",
        "runs_url": "/api/runs"
    }
