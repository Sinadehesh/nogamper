
BEGIN;

CREATE TABLE job_leases (
    job_name    TEXT PRIMARY KEY,

    holder      UUID        NOT NULL,

    acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,

    holder_note TEXT
);


CREATE INDEX idx_job_leases_expiry ON job_leases (expires_at);

ALTER TABLE job_leases ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE job_leases IS
    'Expiring locks for scheduled jobs. Replaces pg_advisory_lock, which '
    'could not be released when a session-mode pooler outlived the worker '
    'that took it. A lease lapses on its own; nothing has to clean it up.';

COMMIT;
