-- Updating analytics tables

SELECT * FROM analytics.f_transaction;
SELECT * FROM analytics.f_conversion;
SELECT * FROM analytics.d_company;
SELECT * FROM analytics.d_currency;
SELECT * FROM analytics.d_time;
SELECT * FROM analytics.f_fx_rate;

SELECT COUNT(*) FROM analytics.f_transaction;
SELECT COUNT(*) FROM analytics.f_conversion;
SELECT COUNT(*) FROM analytics.d_company;
SELECT COUNT(*) FROM analytics.d_currency;
SELECT COUNT(*) FROM analytics.d_time;
SELECT COUNT(*) FROM analytics.f_fx_rate;

TRUNCATE TABLE analytics.f_conversion CASCADE;
TRUNCATE TABLE analytics.f_transaction CASCADE;
TRUNCATE TABLE analytics.f_fx_rate CASCADE;
TRUNCATE TABLE analytics.d_time CASCADE;
TRUNCATE TABLE analytics.d_company CASCADE;
TRUNCATE TABLE analytics.d_currency CASCADE;


SELECT COUNT(*) FROM analytics.f_transaction;


-- Possible LATERAL JOIN hangup
ALTER TABLE analytics.f_conversion DISABLE TRIGGER trg_apply_conversion;