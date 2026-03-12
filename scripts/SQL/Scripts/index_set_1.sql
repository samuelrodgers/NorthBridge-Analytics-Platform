-- These are the operations required to apply the indexes needed 
--     before the second normalized run
-- SQL is produced by Sam Rodgers, comments appended by Claude AI


-- Drop the unique constraint with wrong column order
ALTER TABLE raw.fx_rate
    DROP CONSTRAINT fx_unique;

-- Recreate as named constraint with correct column order
-- Registered in pg_constraint so ON CONFLICT ON CONSTRAINT works
ALTER TABLE raw.fx_rate
    ADD CONSTRAINT idx_fx_rate_cncy_ts
    UNIQUE (base_cncy, quote_cncy, fx_timestamp);

-- BRIN: lightweight block-level filter on ordered timestamp column
CREATE INDEX idx_fx_rate_ts_brin
    ON raw.fx_rate USING brin (fx_timestamp);