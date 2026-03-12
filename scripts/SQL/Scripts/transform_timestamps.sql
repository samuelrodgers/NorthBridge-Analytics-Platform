-- This file is to record the key elements of the LATERAL JOIN
-- that aligns the timestamps for raw transactions<->fx_rates

CREATE INDEX idx_tx_event_cncy_timestamp 
ON raw.transaction_event (base_cncy, quote_cncy, tx_timestamp);

CREATE UNIQUE INDEX fx_unique_idx ON raw.fx_rate USING btree (fx_timestamp, base_cncy, quote_cncy);

-- These two are both sides of the JOIN 
-- The indexes are necessary for efficiency
-- that would not be worth benchmarking


-- Here is the VIEW that would need to be 
-- created to see the JOIN logic (not in the DB)

CREATE OR REPLACE VIEW analytics.v_conversion_candidates AS
SELECT
    t.tx_id,
    t.amount                        AS base_amount,
    COALESCE(t.fee_amount, 0)       AS fee_amount,
    t.base_cncy,
    t.quote_cncy,
    matched_fx.fx_id
FROM raw.transaction_event t
JOIN LATERAL (
    SELECT
        f_analytics.fx_id,
        f_raw.fx_timestamp
    FROM raw.fx_rate f_raw
    JOIN analytics.f_fx_rate f_analytics
      ON  f_analytics.rate       = f_raw.rate
      AND f_analytics.base_cncy  = TRIM(f_raw.base_cncy)
      AND f_analytics.quote_cncy = TRIM(f_raw.quote_cncy)
    WHERE TRIM(f_raw.base_cncy)  = TRIM(t.base_cncy)
      AND TRIM(f_raw.quote_cncy) = TRIM(t.quote_cncy)
      AND f_raw.fx_timestamp    <= t.tx_timestamp
    ORDER BY f_raw.fx_timestamp DESC
    LIMIT 1
) matched_fx ON true
WHERE t.quote_cncy IS NOT NULL;


-- Here is the code that is executed in the python
-- script transform.py

INSERT INTO analytics.f_conversion (base_amount, fee_amount, fx_id, tx_id)
    SELECT
        t.amount                        AS base_amount,
        COALESCE(t.fee_amount, 0)       AS fee_amount,
        matched_fx.fx_id                AS fx_id,
        t.tx_id                         AS tx_id

    FROM raw.transaction_event t

    -- LATERAL JOIN: for each conversion transaction, find the
    -- closest preceding FX rate tick (SQL equivalent of merge_asof)
    JOIN LATERAL (
        SELECT
            f_analytics.fx_id,
            f_raw.fx_timestamp
        FROM raw.fx_rate f_raw
        JOIN analytics.f_fx_rate f_analytics
          ON  f_analytics.rate       = f_raw.rate
          AND f_analytics.base_cncy  = TRIM(f_raw.base_cncy)
          AND f_analytics.quote_cncy = TRIM(f_raw.quote_cncy)
        WHERE TRIM(f_raw.base_cncy)  = TRIM(t.base_cncy)
          AND TRIM(f_raw.quote_cncy) = TRIM(t.quote_cncy)
          AND f_raw.fx_timestamp    <= t.tx_timestamp
        ORDER BY f_raw.fx_timestamp DESC
        LIMIT 1
    ) matched_fx ON true

    -- Only rows where a conversion is needed (customer paid in foreign currency)
    WHERE t.quote_cncy IS NOT NULL

    -- Idempotency: skip if already converted
    AND NOT EXISTS (
        SELECT 1
        FROM analytics.f_conversion fc
        WHERE fc.tx_id = t.tx_id
    )