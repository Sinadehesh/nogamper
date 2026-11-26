
BEGIN;

CREATE TABLE job_runs (
    job_name         TEXT PRIMARY KEY,

    started_at       TIMESTAMPTZ NOT NULL,
    finished_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds NUMERIC(10,3) NOT NULL CHECK (duration_seconds >= 0),

    outcome          TEXT NOT NULL CHECK (outcome IN ('ok', 'error', 'deadline')),

    detail           JSONB NOT NULL DEFAULT '{}'::JSONB,

    holder_note      TEXT
);

ALTER TABLE job_runs ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE job_runs IS
    'How each job''s last run went. Exists so "why is it stuck" is answerable '
    'from the admin page rather than from a log the operator cannot reach.';

COMMIT;
