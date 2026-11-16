-- Question: Of the customers who made their first purchase in a given month,
--   what share came back and ordered again in each later month?
-- Tables: olist.order_revenue (delivered orders in the analysis window).
-- Technique: CTEs for first-purchase cohorts, a cohort-by-offset grid built
--   with generate_series (Postgres-specific), LEFT JOIN against observed
--   activity. Output is one row per cohort month and month offset.
-- Assumptions:
--   * Customers are identified by customer_unique_id. customer_id changes
--     with every order and would make retention exactly zero.
--   * A cohort cell that lies beyond the end of the window cannot be
--     observed and is NULL. A cell with no returning customers is 0.
--   * Offset 0 is 100 percent by construction (the first purchase itself).

WITH bounds AS (
    SELECT MIN(purchase_month) AS first_month,
           MAX(purchase_month) AS last_month
    FROM olist.order_revenue
),

first_purchase AS (
    SELECT customer_unique_id,
           MIN(purchase_month) AS cohort_month
    FROM olist.order_revenue
    GROUP BY customer_unique_id
),

cohort_sizes AS (
    SELECT cohort_month,
           COUNT(*) AS cohort_size
    FROM first_purchase
    GROUP BY cohort_month
),

-- One row per customer per calendar month in which they ordered.
activity AS (
    SELECT DISTINCT f.customer_unique_id,
                    f.cohort_month,
                    r.purchase_month
    FROM olist.order_revenue r
    JOIN first_purchase f ON f.customer_unique_id = r.customer_unique_id
),

retained AS (
    SELECT cohort_month,
           (EXTRACT(YEAR  FROM age(purchase_month, cohort_month)) * 12
          + EXTRACT(MONTH FROM age(purchase_month, cohort_month)))::int AS month_offset,
           COUNT(*) AS active_customers
    FROM activity
    GROUP BY 1, 2
),

-- Full cohort-by-offset grid, including offsets where nobody returned.
grid AS (
    SELECT cs.cohort_month,
           cs.cohort_size,
           gs.month_offset,
           CAST(cs.cohort_month + make_interval(months => gs.month_offset) AS date)
               AS activity_month
    FROM cohort_sizes cs
    CROSS JOIN bounds b
    CROSS JOIN LATERAL generate_series(
        0,
        (EXTRACT(YEAR  FROM age(b.last_month, b.first_month)) * 12
       + EXTRACT(MONTH FROM age(b.last_month, b.first_month)))::int
    ) AS gs(month_offset)
)

SELECT g.cohort_month,
       g.cohort_size,
       g.month_offset,
       -- Cells after the end of the window are unobservable and stay NULL.
       CASE WHEN g.activity_month > b.last_month THEN NULL
            ELSE COALESCE(r.active_customers, 0)
       END AS active_customers,
       CASE WHEN g.activity_month > b.last_month THEN NULL
            ELSE ROUND(100.0 * COALESCE(r.active_customers, 0) / g.cohort_size, 2)
       END AS retention_pct
FROM grid g
CROSS JOIN bounds b
LEFT JOIN retained r
       ON r.cohort_month = g.cohort_month
      AND r.month_offset = g.month_offset
ORDER BY g.cohort_month, g.month_offset;
