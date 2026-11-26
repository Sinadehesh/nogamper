WITH m AS (
    SELECT count(*)                                            AS total,
           count(*) FILTER (WHERE status = 'ACTIVE')           AS active,
           count(*) FILTER (WHERE status = 'LOCKED')           AS locked,
           count(*) FILTER (WHERE status = 'ACTIVE'
                              AND price_updated_at > NOW() - INTERVAL '90 seconds') AS fresh,
           EXTRACT(EPOCH FROM (NOW() - max(price_updated_at)
                   FILTER (WHERE status = 'ACTIVE')))          AS since_newest
      FROM markets
),
j AS (
    SELECT count(*) AS held,
           max(EXTRACT(EPOCH FROM (NOW() - acquired_at))) AS longest_held,
           string_agg(job_name || ' (' ||
                      round(EXTRACT(EPOCH FROM (NOW() - acquired_at))/60) || 'm, ' ||
                      COALESCE(holder_note,'?') || ')', ', ') AS holders
      FROM job_leases
)
SELECT
    CASE
        WHEN m.total  = 0 THEN 'DISCOVERY — no markets at all. Discovery has never ingested.'
        WHEN m.active = 0 THEN 'DISCOVERY — every market is locked/expired, nothing to price.'
        WHEN j.longest_held >= 300
             THEN 'WORKER — a job has been running far too long. The lock is fine; the job is not finishing.'
        WHEN m.since_newest > 90 AND j.held = 0
             THEN 'WORKER — prices are old and no job holds a lease. Nothing is running the sync.'
        WHEN m.since_newest > 90
             THEN 'UPSTREAM — the job runs but no price lands. The CLOB is returning nothing usable.'
        WHEN m.active > m.fresh
             THEN 'DEGRADED — some markets past the window, newest is current. Pass truncating under load.'
        ELSE 'HEALTHY — prices are current. If the app disagrees, suspect Redis.'
    END                                              AS verdict,
    m.total          AS markets_total,
    m.active         AS markets_active,
    m.locked         AS markets_locked,
    m.fresh          AS markets_fresh,
    m.active - m.fresh                               AS markets_stale,
    round(m.since_newest)                            AS seconds_since_newest_price,
    round(m.since_newest / 60, 1)                    AS minutes_since_newest_price,
    j.held                                           AS jobs_holding_a_lease,
    COALESCE(j.holders, 'none')                      AS lease_holders
  FROM m, j;
