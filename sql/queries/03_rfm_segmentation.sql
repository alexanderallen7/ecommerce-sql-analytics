-- Question: How do customers break down into recency, frequency, and monetary
--   segments, and which segments carry the revenue?
-- Tables: olist.order_revenue, olist.analysis_window.
-- Technique: per-customer CTE, NTILE(5) window scores for recency and
--   monetary, a rule-based frequency score, CASE mapping to named segments.
-- Assumptions:
--   * Customers are identified by customer_unique_id.
--   * Recency is measured against the day after the analysis window ends
--     (2018-09-01), so it does not depend on when the query is run.
--   * Honesty note on frequency: 96.9 percent of customers in the window
--     bought exactly once, so NTILE on frequency would split identical
--     one-purchase customers into arbitrary quintiles. Frequency is scored
--     with a direct rule instead: 1 order = 1, 2 orders = 2, 3 or more = 3.
--     Segments are therefore driven mainly by recency and monetary value,
--     with repeat purchase as an overriding flag.

WITH customer_rfm AS (
    SELECT r.customer_unique_id,
           (w.window_end_exclusive - MAX(r.order_purchase_timestamp)::date)
               AS recency_days,
           COUNT(*)       AS frequency,
           SUM(r.revenue) AS monetary
    FROM olist.order_revenue r
    CROSS JOIN olist.analysis_window w
    GROUP BY r.customer_unique_id, w.window_end_exclusive
),

scored AS (
    SELECT customer_unique_id,
           recency_days,
           frequency,
           monetary,
           -- NTILE(5) over ascending recency puts the most recent buyers in
           -- tile 1; subtracting from 6 makes 5 the best score.
           6 - NTILE(5) OVER (ORDER BY recency_days) AS r_score,
           NTILE(5) OVER (ORDER BY monetary)         AS m_score,
           CASE
               WHEN frequency >= 3 THEN 3
               WHEN frequency = 2  THEN 2
               ELSE 1
           END AS f_score
    FROM customer_rfm
),

segmented AS (
    SELECT *,
           CASE
               WHEN f_score >= 2 AND r_score >= 4 THEN 'Active repeat'
               WHEN f_score >= 2                  THEN 'Lapsed repeat'
               WHEN r_score >= 4 AND m_score >= 4 THEN 'Recent high value'
               WHEN r_score >= 4                  THEN 'Recent low value'
               WHEN r_score <= 2 AND m_score >= 4 THEN 'Lapsed high value'
               WHEN r_score <= 2                  THEN 'Lapsed low value'
               ELSE 'Middle'
           END AS segment
    FROM scored
)

SELECT segment,
       COUNT(*)                                             AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)   AS pct_customers,
       ROUND(SUM(monetary), 2)                              AS revenue,
       ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1)
                                                            AS pct_revenue,
       ROUND(AVG(recency_days), 0)                          AS avg_recency_days,
       ROUND(AVG(frequency), 2)                             AS avg_frequency,
       ROUND(AVG(monetary), 2)                              AS avg_monetary
FROM segmented
GROUP BY segment
ORDER BY revenue DESC;
