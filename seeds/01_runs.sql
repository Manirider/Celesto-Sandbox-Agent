-- Ensure schema exists
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

-- Idempotent seed
INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
VALUES ('seed-demo-1', 'sbx-seeddemo1', 'demo-problem', 'deleted', 'celesto_sandbox')
ON CONFLICT (run_id) DO NOTHING;
