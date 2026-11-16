-- Question: What does daily revenue look like once day-to-day noise is
--   smoothed with a 30-day rolling sum, and how does cumulative revenue grow?
-- Tables: olist.order_revenue, olist.analysis_window.
-- Technique: a date spine built with generate_series (Postgres-specific) so
--   that days with no delivered orders appear as 0 revenue, then two window
--   sums with explicit ROWS frames. The ROWS frame counts days correctly
--   only because the spine guarantees exactly one row per calendar day.
-- Assumption: the first 29 days have a partial rolling window (fewer than 30
--   days of history); they are flagged in rolling_window_complete.

WITH spine AS (
    SELECT CAST(gs AS date) AS day
    FROM olist.analysis_window w
    CROSS JOIN LATERAL generate_series(
        w.window_start,
        w.window_end_exclusive - 1,
        INTERVAL '1 day'
    ) AS gs
),

daily AS (
    SELECT CAST(order_purchase_timestamp AS date) AS day,
           SUM(revenue) AS revenue
    FROM olist.order_revenue
    GROUP BY 1
)

SELECT s.day,
       ROUND(COALESCE(d.revenue, 0), 2) AS revenue,
       ROUND(SUM(COALESCE(d.revenue, 0)) OVER (
           ORDER BY s.day
           ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
       ), 2) AS rolling_30d_revenue,
       ROUND(SUM(COALESCE(d.revenue, 0)) OVER (
           ORDER BY s.day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ), 2) AS cumulative_revenue,
       ROW_NUMBER() OVER (ORDER BY s.day) >= 30 AS rolling_window_complete
FROM spine s
LEFT JOIN daily d ON d.day = s.day
ORDER BY s.day;
