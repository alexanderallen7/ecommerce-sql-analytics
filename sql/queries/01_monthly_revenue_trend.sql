-- Question: How did monthly revenue, order count, and average order value
--   develop over the analysis window, and how large are the swings from one
--   month to the next?
-- Tables: olist.order_revenue (delivered orders, Jan 2017 to Aug 2018,
--   revenue = item price + freight; defined in sql/schema/03_derived.sql)
-- Technique: GROUP BY month in a CTE, then LAG() window functions for
--   month-over-month change.
-- Assumption: orders are dated by purchase timestamp.

WITH monthly AS (
    SELECT purchase_month,
           SUM(revenue) AS revenue,
           COUNT(*)     AS order_count
    FROM olist.order_revenue
    GROUP BY purchase_month
)

SELECT purchase_month,
       ROUND(revenue, 2)               AS revenue,
       order_count,
       ROUND(revenue / order_count, 2) AS avg_order_value,
       -- LAG(revenue) is NULL for the first month, so the change is NULL
       -- there instead of a fake 0.
       ROUND(
           100.0 * (revenue - LAG(revenue) OVER (ORDER BY purchase_month))
                 / LAG(revenue) OVER (ORDER BY purchase_month),
           1
       ) AS revenue_mom_pct,
       ROUND(
           100.0 * (order_count - LAG(order_count) OVER (ORDER BY purchase_month))
                 / LAG(order_count) OVER (ORDER BY purchase_month),
           1
       ) AS orders_mom_pct
FROM monthly
ORDER BY purchase_month;
