-- Migration 011: Backfill revenue_growth_rate for historical f_industry rows
--
-- On an initial historical seed, SQL_REFRESH_FINDUSTRY uses a LATERAL lookup
-- to find the prior period's revenue. Because all rows are inserted in a single
-- statement, none are visible to each other during execution, so every row gets
-- revenue_growth_rate = NULL.
--
-- This migration fills in those NULLs using LAG() which operates over all
-- already-committed rows at once. Only NULL rows are touched — any rows already
-- populated by CRON runs are left unchanged.
--
-- Safe to run multiple times (idempotent — WHERE revenue_growth_rate IS NULL).
-- Run after a historical seed: python transform.py --seed && psql ... -f 011_...sql

WITH growth_calc AS (
    SELECT
        fi.industry_id,
        fi.time_id,
        CASE
            WHEN LAG(fi.total_revenue) OVER (
                     PARTITION BY fi.industry_id ORDER BY dt.t_stamp
                 ) IS NULL
                THEN NULL
            WHEN LAG(fi.total_revenue) OVER (
                     PARTITION BY fi.industry_id ORDER BY dt.t_stamp
                 ) = 0
                THEN NULL
            WHEN ABS(
                ROUND(
                    (fi.total_revenue
                        - LAG(fi.total_revenue) OVER (
                              PARTITION BY fi.industry_id ORDER BY dt.t_stamp
                          )
                    ) / LAG(fi.total_revenue) OVER (
                              PARTITION BY fi.industry_id ORDER BY dt.t_stamp
                          ) * 100,
                    4
                )
            ) >= 1000
                THEN NULL
            ELSE
                ROUND(
                    (fi.total_revenue
                        - LAG(fi.total_revenue) OVER (
                              PARTITION BY fi.industry_id ORDER BY dt.t_stamp
                          )
                    ) / LAG(fi.total_revenue) OVER (
                              PARTITION BY fi.industry_id ORDER BY dt.t_stamp
                          ) * 100,
                    4
                )
        END AS computed_growth
    FROM analytics.f_industry fi
    JOIN analytics.d_time dt
      ON fi.time_id = dt.time_id
)
UPDATE analytics.f_industry fi
SET    revenue_growth_rate = gc.computed_growth
FROM   growth_calc gc
WHERE  fi.industry_id          = gc.industry_id
  AND  fi.time_id              = gc.time_id
  AND  fi.revenue_growth_rate  IS NULL;
