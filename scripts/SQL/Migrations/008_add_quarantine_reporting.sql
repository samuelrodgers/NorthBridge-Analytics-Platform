-- Migration 008: Add quarantine reporting infrastructure
-- Description: Adds batch_id to raw.transaction_event for pipeline run grouping,
--              and creates raw.quarantine_event to persist Python-layer validation
--              failures from pipeline.py's _split_quarantine().
--
--              raw.quarantine_event captures rows that failed normalization and
--              never reached raw.transaction_event. A separate SQL-layer view
--              (analytics.v_quarantine_log) will cover rows that made it into raw
--              but fail analytics validation rules. Together they feed a unified
--              quarantine dashboard.
--
-- Depends on:  007 (raw.prevent_modification must exist)
-- Safe to run: Yes — additive only.

BEGIN;

-- ── batch_id on transaction_event ────────────────────────────────────────────
-- Stamps every row with the pipeline run UUID so Phase 1 analysis can group
-- failures and clean rows by ingestion batch.

ALTER TABLE raw.transaction_event
    ADD COLUMN IF NOT EXISTS batch_id UUID DEFAULT NULL;

-- ── raw.quarantine_event ─────────────────────────────────────────────────────
-- Grain: one row per violation per transaction. A transaction that fails two
-- rules produces two records, linked by tx_id. This mirrors the UNION ALL
-- design planned for analytics.v_quarantine_log.
--
-- Columns carry the original transaction values at the time of quarantine so
-- that analysts can inspect what went wrong without needing the Python logs.

CREATE TABLE raw.quarantine_event (
    quarantine_id        UUID                     DEFAULT gen_random_uuid() NOT NULL,
    tx_id                UUID,
    c_id                 UUID,
    base_cncy            VARCHAR(3),
    quote_cncy           VARCHAR(3),
    amount               NUMERIC(18,4),
    fee_amount           NUMERIC(16,4),
    tx_timestamp         TIMESTAMP WITH TIME ZONE,
    failure_code         VARCHAR(40)              NOT NULL,
    failure_reason       VARCHAR(200)             NOT NULL,
    batch_id             UUID,
    ingestion_timestamp  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT quarantine_event_pkey PRIMARY KEY (quarantine_id)
);

ALTER TABLE raw.quarantine_event OWNER TO alex_analytics;

-- Index for dashboard queries: filter by batch, then by failure type
CREATE INDEX idx_quarantine_event_batch_id
    ON raw.quarantine_event USING btree (batch_id);

CREATE INDEX idx_quarantine_event_failure_code
    ON raw.quarantine_event USING btree (failure_code);

-- Append-only: consistent with all raw schema tables
CREATE TRIGGER trg_quarantine_event_prevent_modification
    BEFORE UPDATE OR DELETE ON raw.quarantine_event
    FOR EACH ROW EXECUTE FUNCTION raw.prevent_modification();

COMMIT;
