-- Migration 015: Batch ingestion log table
-- Description: Persists per-run pipeline stats that main.py currently prints
--              to stdout and discards. Enables governance page to show
--              ingestion history and per-batch pass rates without scanning
--              tens of millions of raw transaction rows.
--
-- Columns:
--   batch_id         — matches the UUID stamped on every raw.transaction_event
--                      and raw.quarantine_event row for that run; natural PK.
--   run_timestamp    — wall-clock time the run completed (DEFAULT NOW()).
--   window_start     — synthetic tx timestamp range start for this batch.
--   window_end       — synthetic tx timestamp range end for this batch.
--   rows_received    — total transactions generated before noise/normalisation.
--   rows_loaded      — clean rows inserted into raw.transaction_event.
--   rows_quarantined — rows diverted to raw.quarantine_event.
--   noise_level      — 'low' | 'medium' | 'high' as passed to main.py.
--
-- Depends on: nothing (self-contained raw schema table)

BEGIN;

CREATE TABLE raw.batch_log (
    batch_id         UUID         PRIMARY KEY,
    run_timestamp    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    window_start     TIMESTAMPTZ,
    window_end       TIMESTAMPTZ,
    rows_received    INT          NOT NULL,
    rows_loaded      INT          NOT NULL,
    rows_quarantined INT          NOT NULL,
    noise_level      VARCHAR(10)
);

COMMENT ON TABLE raw.batch_log IS
    'One row per main.py run. Used by governance page for ingestion history.';

COMMIT;
