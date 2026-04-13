-- tx_industry_benchmark
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
industry metrics with hq_country for country-level filtering.
built from f_transaction + f_expense via CTEs to avoid row multiplication.
granularity: (industry, country, time) — charts aggregate further as needed.
loses revenue_growth_rate (pre-computed in transform, all NULL anyway).

if performance is too slow, revert to the original below.
*/
SELECT
  di.industry_id,
  di.name                                                                        AS industry_name,
  co.hq_country,
  dt.t_stamp,
  dt.fisc_quarter,
  ROUND(SUM(ft.amount), 2)                                                       AS total_revenue,
  COUNT(ft.tx_id)                                                                AS transaction_count,
  COUNT(DISTINCT ft.c_id)                                                        AS company_count,
  ROUND(SUM(ft.amount) / NULLIF(COUNT(DISTINCT ft.c_id), 0), 2)                  AS avg_revenue_per_co
FROM analytics.f_transaction ft
JOIN analytics.d_company  co ON ft.c_id        = co.c_id
JOIN analytics.d_industry di ON co.industry_id  = di.industry_id
JOIN analytics.d_time     dt ON ft.time_id      = dt.time_id
GROUP BY di.industry_id, di.name, co.hq_country, dt.t_stamp, dt.fisc_quarter

/*
-- ORIGINAL (fast, from f_industry pre-aggregate, no country filter possible):
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
*/

-- tx_running_revenue
/*
cumulative revenue per company per day using a window function — powers Q5 on analytics.html
SUM OVER PARTITION BY c_id ORDER BY day gives the running total; day grain avoids minute-level row explosion
*/
SELECT
    dc.c_name,
    DATE_TRUNC('day', dt.t_stamp)              AS day_bucket,
    ROUND(SUM(ft.amount), 2)                   AS bucket_revenue_usd,
    ROUND(SUM(SUM(ft.amount)) OVER (
        PARTITION BY dc.c_id
        ORDER BY DATE_TRUNC('day', dt.t_stamp)
    ), 2)                                       AS running_revenue_usd
FROM analytics.f_transaction ft
JOIN analytics.d_time dt    ON ft.time_id = dt.time_id
JOIN analytics.d_company dc ON ft.c_id    = dc.c_id
GROUP BY dc.c_id, dc.c_name, DATE_TRUNC('day', dt.t_stamp)
ORDER BY dc.c_name, day_bucket

-- fx_currency_mix
/*
transaction count and total amount by currency — shows platform FX exposure (Q3 chart on fx.html)
*/
SELECT
    ft.cncy                  AS currency,
    COUNT(ft.tx_id)          AS transaction_count,
    ROUND(SUM(ft.amount), 2) AS total_amount
FROM analytics.f_transaction ft
GROUP BY ft.cncy
ORDER BY transaction_count DESC

-- fx_fee_burden
/*
total FX fee revenue per company — larger companies generate more fee volume (Q4 chart on fx.html)
*/
SELECT
    dc.c_name,
    COUNT(fc.cx_id)              AS conversion_count,
    ROUND(SUM(fc.fee_amount), 2) AS total_fees_usd
FROM analytics.f_conversion fc
JOIN analytics.f_transaction ft ON fc.tx_id = ft.tx_id
JOIN analytics.d_company dc ON ft.c_id = dc.c_id
GROUP BY dc.c_id, dc.c_name
ORDER BY total_fees_usd DESC