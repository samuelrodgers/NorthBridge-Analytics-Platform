-- Migration 010: Add unique constraint to analytics.d_time.t_stamp
--
-- Without this, SQL_INSERT_DTIME's NOT EXISTS guard is the only protection
-- against duplicate timestamps. If two raw rows share a timestamp, both pass
-- the NOT EXISTS check (neither is in d_time at query start) and two d_time
-- rows are created with the same t_stamp. Downstream joins in SQL_INSERT_FEXPENSE
-- and SQL_INSERT_FTRANSACTION would then produce duplicate fact rows.
--
-- Note: if this fails with "could not create unique index" there are already
-- duplicate t_stamp values present. Resolve with:
--   DELETE FROM analytics.d_time a USING analytics.d_time b
--   WHERE a.time_id > b.time_id AND a.t_stamp = b.t_stamp;
-- then re-run this migration.

ALTER TABLE analytics.d_time
    ADD CONSTRAINT uq_d_time_stamp UNIQUE (t_stamp);
