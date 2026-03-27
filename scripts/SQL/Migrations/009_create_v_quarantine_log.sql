-- Migration 009: Create analytics.v_quarantine_log
-- Description: Unified view over both quarantine sources for reporting.
--
--   Source A — raw.quarantine_event
--     Python-layer failures: rows that failed normalization in pipeline.py
--     and never reached raw.transaction_event.
--
--   Source B — raw.transaction_event (6 SQL-layer rules)
--     Rows that made it into raw but fail validation against the analytics
--     schema. Each rule is a separate SELECT so a row can appear multiple
--     times if it violates multiple rules (same shape as Source A).
--
-- SQL-layer rules:
--   NULL_COMPANY_ID      — c_id IS NULL
--   INVALID_AMOUNT       — amount IS NULL OR amount <= 0
--   UNKNOWN_COMPANY      — c_id not in analytics.d_company (non-null c_id only)
--   INVALID_BASE_CURRENCY — base_cncy not in analytics.d_currency
--   DUPLICATE_TX_ID      — tx_id appears more than once in raw.transaction_event
--   NULL_TIMESTAMP       — tx_timestamp IS NULL
--
-- batch_id will be NULL for transaction_event rows that predate migration 008.
--
-- Depends on: 008 (raw.quarantine_event must exist)

CREATE OR REPLACE VIEW analytics.v_quarantine_log AS

WITH

-- Pre-compute duplicate counts once so the DUPLICATE_TX_ID rule
-- doesn't need a subquery of its own.
tx_annotated AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY tx_id) AS _dup_count
    FROM raw.transaction_event
),

sql_layer AS (

    -- NULL_COMPANY_ID
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        'NULL_COMPANY_ID'::VARCHAR(40)                   AS failure_code,
        'c_id is null'::VARCHAR(200)                     AS failure_reason,
        'sql_layer'::TEXT                                AS source
    FROM tx_annotated
    WHERE c_id IS NULL

    UNION ALL

    -- INVALID_AMOUNT
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        'INVALID_AMOUNT'::VARCHAR(40),
        'amount is null or non-positive'::VARCHAR(200),
        'sql_layer'::TEXT
    FROM tx_annotated
    WHERE amount IS NULL OR amount <= 0

    UNION ALL

    -- UNKNOWN_COMPANY — only fires when c_id is non-null but not in d_company.
    -- NULL c_id is handled by NULL_COMPANY_ID above.
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        'UNKNOWN_COMPANY'::VARCHAR(40),
        'c_id not found in analytics.d_company'::VARCHAR(200),
        'sql_layer'::TEXT
    FROM tx_annotated
    WHERE c_id IS NOT NULL
      AND c_id NOT IN (SELECT c_id FROM analytics.d_company)

    UNION ALL

    -- INVALID_BASE_CURRENCY
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        'INVALID_BASE_CURRENCY'::VARCHAR(40),
        'base_cncy not found in analytics.d_currency'::VARCHAR(200),
        'sql_layer'::TEXT
    FROM tx_annotated
    WHERE base_cncy NOT IN (SELECT cncy_code FROM analytics.d_currency)

    UNION ALL

    -- DUPLICATE_TX_ID — uses pre-computed _dup_count
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        'DUPLICATE_TX_ID'::VARCHAR(40),
        'tx_id appears more than once in raw.transaction_event'::VARCHAR(200),
        'sql_layer'::TEXT
    FROM tx_annotated
    WHERE _dup_count > 1

    UNION ALL

    -- NULL_TIMESTAMP
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        'NULL_TIMESTAMP'::VARCHAR(40),
        'tx_timestamp is null'::VARCHAR(200),
        'sql_layer'::TEXT
    FROM tx_annotated
    WHERE tx_timestamp IS NULL
),

python_layer AS (
    SELECT
        tx_id, c_id, base_cncy, tx_timestamp, amount, fee_amount, quote_cncy,
        ingestion_timestamp, batch_id,
        failure_code,
        failure_reason,
        'python_layer'::TEXT AS source
    FROM raw.quarantine_event
)

SELECT * FROM python_layer
UNION ALL
SELECT * FROM sql_layer;
