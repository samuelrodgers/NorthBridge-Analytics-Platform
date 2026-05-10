-- 1. Breakdown by failure code
  SELECT failure_code, COUNT(*) as violations, COUNT(DISTINCT tx_id) as unique_transactions
  FROM raw.quarantine_event
  GROUP BY failure_code ORDER BY violations DESC;

  -- 2. Transactions with multiple failures
  SELECT tx_id, COUNT(*) as failure_count, array_agg(failure_code) as codes
  FROM raw.quarantine_event
  GROUP BY tx_id HAVING COUNT(*) > 1
  LIMIT 10;

  -- 3. Batch ID is populated
  SELECT batch_id, COUNT(*) as rows, MIN(ingestion_timestamp) as run_time
  FROM raw.quarantine_event
  GROUP BY batch_id ORDER BY run_time DESC LIMIT 5;


