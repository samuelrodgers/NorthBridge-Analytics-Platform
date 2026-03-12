-- These are the operations required to apply the indexes needed 
--     before the second normalized run
-- SQL is produced by Sam Rodgers, comments appended by Claude AI


-- B-tree on f_transaction FK to d_company: supports Q1, Q4, Q5
CREATE INDEX idx_f_transaction_c_id
    ON analytics.f_transaction (c_id);

-- B-tree on f_transaction FK to d_time: supports Q2, Q5
CREATE INDEX idx_f_transaction_time_id
    ON analytics.f_transaction (time_id);