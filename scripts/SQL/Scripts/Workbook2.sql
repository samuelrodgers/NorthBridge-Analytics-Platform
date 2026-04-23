-- Update raw tables
SELECT * FROM raw.transaction_event;
SELECT * FROM raw.fx_rate;
SELECT * FROM raw.quarantine_event;

SELECT COUNT(*) FROM raw.transaction_event;
SELECT COUNT(*) FROM raw.fx_rate;
SELECT COUNT(*) FROM raw.quarantine_event;


TRUNCATE TABLE raw.transaction_event CASCADE;
TRUNCATE TABLE raw.fx_rate CASCADE;
TRUNCATE TABLE raw.quarantine_event CASCADE;
TRUNCATE TABLE raw.batch_log CASCADE;
TRUNCATE TABLE raw.expense_event CASCADE;
TRUNCATE TABLE raw.quarantine_resolution CASCADE;
TRUNCATE TABLE raw.pipeline_run CASCADE;



ALTER TABLE raw.transaction_event RENAME COLUMN cncy_code TO base_cncy;
ALTER TABLE raw.transaction_event ALTER COLUMN base_cncy TYPE char(3);
ALTER TABLE raw.fx_rate ALTER COLUMN base_cncy TYPE char(3);
ALTER TABLE raw.fx_rate ALTER COLUMN quote_cncy TYPE char(3);
ALTER TABLE raw.transaction_event ADD COLUMN quote_cncy char(3);
ALTER TABLE raw.transaction_event ADD COLUMN fee_amount char(3);

ALTER TABLE raw.fx_rate ALTER COLUMN fx_rate_id SET DEFAULT gen_random_uuid();

ALTER TABLE raw.transaction_event ALTER COLUMN c_id TYPE uuid USING c_id::uuid;
