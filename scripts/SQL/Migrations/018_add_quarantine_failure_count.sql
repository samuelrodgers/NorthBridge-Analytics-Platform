-- Migration 018: Add failure_count to raw.quarantine_event
-- Description: Adds a failure_count column that records how many quarantine
--              records were produced for the same tx_id within a single batch.
--
--              A transaction that violates one rule gets failure_count = 1.
--              A transaction that violates three rules gets failure_count = 3
--              on all three of its quarantine rows.
--
--              The value is computed in Python by load_quarantine() before the
--              INSERT, so no SQL window function is needed at query time.
--              Existing rows are backfilled to the DEFAULT of 1 (one recorded
--              violation per row, which is the minimum possible).
--
-- Depends on:  008 (raw.quarantine_event must exist)
-- Renumbered from 013 — avoids collision with pipeline-rework migration sequence.
-- Safe to run: Yes — uses ADD COLUMN IF NOT EXISTS, additive only.

BEGIN;

ALTER TABLE raw.quarantine_event
    ADD COLUMN IF NOT EXISTS failure_count SMALLINT NOT NULL DEFAULT 1;

COMMENT ON COLUMN raw.quarantine_event.failure_count IS
    'Number of quarantine records that share this tx_id within the same batch. '
    'Computed in Python before INSERT. Existing rows default to 1.';

COMMIT;
