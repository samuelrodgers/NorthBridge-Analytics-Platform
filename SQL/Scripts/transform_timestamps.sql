-- This file is to record the key elements of the LATERAL JOIN
-- that aligns the timestamps for raw transactions<->fx_rates

CREATE INDEX idx_tx_event_cncy_timestamp 
ON raw.transaction_event (base_cncy, quote_cncy, tx_timestamp);

CREATE UNIQUE INDEX fx_unique_idx ON raw.fx_rate USING btree (fx_timestamp, base_cncy, quote_cncy);

-- These two are both sides of the JOIN 
-- The indexes are necessary for efficiency
-- that would not be worth benchmarking


-- Here is the JOIN statement
-- (I obviously have not written it yet,
-- I am waiting until I validate transform.py logic)