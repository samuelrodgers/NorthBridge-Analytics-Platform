-- Migration 012: Quarantine dedup constraint
-- Description: Adds a UNIQUE constraint on raw.quarantine_event
--              (batch_id, tx_id, failure_code) so that re-running the same
--              pipeline batch cannot insert duplicate quarantine records.
--
--              NULLS NOT DISTINCT (PostgreSQL 15+) treats NULL tx_id values
--              as equal so that python-layer failures without a tx_id also
--              deduplicate correctly within the same batch.
--
-- Depends on:  008 (raw.quarantine_event must exist)
-- Safe to run: Yes — additive only, no data modified.

BEGIN;

ALTER TABLE raw.quarantine_event
    ADD CONSTRAINT uq_quarantine_dedup
    UNIQUE NULLS NOT DISTINCT (batch_id, tx_id, failure_code);

COMMIT;
