-- industry_benchmark
/*
the company vs industry avg comparison, name reflects it joins transactions to the industry aggregate for benchmarking
*/
SELECT
  dt.t_stamp,
  SUM(t.amount)              AS company_revenue,
  AVG(fi.avg_revenue_per_co) AS industry_avg
FROM analytics.f_transaction t
JOIN analytics.d_time     dt ON t.time_id    = dt.time_id
JOIN analytics.d_company  co ON t.c_id       = co.c_id
JOIN analytics.f_industry fi ON co.industry_id = fi.industry_id
  AND fi.time_id = t.time_id
GROUP BY dt.t_stamp

-- expense_detail
/*
 expense fact with category, company, industry and time, the core expense drill-down dataset
*/
SELECT
  e.expense_id,
  e.amount        AS expense_amount,
  e.cncy,
  ec.category_name,
  co.c_id,
  co.c_name,
  di.name         AS industry_name,
  dt.t_stamp,
  dt.fisc_quarter
FROM analytics.f_expense e
JOIN analytics.d_company          co ON e.c_id        = co.c_id
JOIN analytics.d_industry         di ON co.industry_id = di.industry_id
JOIN analytics.d_expense_category ec ON e.category_id  = ec.category_id
JOIN analytics.d_time             dt ON e.time_id      = dt.time_id

-- tx_detail
/*
the full transaction dataset with company and industry dims, your most-used general purpose dataset
*/
SELECT
  t.tx_id,
  t.amount        AS revenue,
  t.cncy,
  co.c_id,
  co.c_name,
  co.hq_country,
  co.default_cncy,
  di.name         AS industry_name,
  di.display_cncy AS industry_display_cncy,
  dt.t_stamp,
  dt.fisc_quarter,
  dt.day_of_week
FROM analytics.f_transaction t
JOIN analytics.d_company  co ON t.c_id      = co.c_id
JOIN analytics.d_industry di ON co.industry_id = di.industry_id
JOIN analytics.d_time     dt ON t.time_id   = dt.time_id

-- revenue_vs_expenses
/*
the UNION ALL dataset, name makes the purpose immediately obvious
*/
SELECT
  d.t_stamp,
  t.amount,
  'Revenue' AS series
FROM analytics.f_transaction t
JOIN analytics.d_time d ON t.time_id = d.time_id

UNION ALL

SELECT
  d.t_stamp,
  e.amount,
  'Expenses' AS series
FROM analytics.f_expense e
JOIN analytics.d_time d ON e.time_id = d.time_id

-- tx_company
/*
transaction with time and company name, the simpler transaction dataset without industry
*/
SELECT
  t.tx_id,
  t.amount,
  t.c_id,
  t.cncy,
  d.t_stamp,
  d.fisc_quarter,
  d.day_of_week,
  co.c_name
FROM analytics.f_transaction t
JOIN analytics.d_time d ON t.time_id = d.time_id
JOIN analytics.d_company co ON t.c_id = co.c_id

-- industry_detail
/*
the f_industry pre-aggregate with time and industry name resolved, your base dataset for all industry-level charts
*/
SELECT
  fi.industry_id,
  fi.total_revenue,
  fi.total_expenses,
  fi.net_profit,
  fi.transaction_count,
  fi.avg_revenue_per_co,
  fi.revenue_growth_rate,
  fi.company_count,
  d.t_stamp,
  d.fisc_quarter,
  di.name AS industry_name
FROM analytics.f_industry fi
JOIN analytics.d_time d ON fi.time_id = d.time_id
JOIN analytics.d_industry di ON fi.industry_id = di.industry_id