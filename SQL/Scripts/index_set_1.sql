-- These are the operations required to apply the indexes needed 
--     before the second normalized run
-- SQL is produced by Sam Rodgers, comments appended by Claude AI


-- Drop the unique constraint with wrong column order
-- Uniqueness is preserved by the new B-tree index below
ALTER TABLE raw.fx_rate
    DROP CONSTRAINT fx_unique;

-- B-tree: optimizes LATERAL JOIN currency pair equality + timestamp range lookup
CREATE UNIQUE INDEX idx_fx_rate_cncy_ts
    ON raw.fx_rate (base_cncy, quote_cncy, fx_timestamp);

-- BRIN: lightweight block-level filter on ordered timestamp column
CREATE INDEX idx_fx_rate_ts_brin
    ON raw.fx_rate USING brin (fx_timestamp);