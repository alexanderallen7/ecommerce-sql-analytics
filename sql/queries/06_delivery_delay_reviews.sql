-- Question: How do review scores differ between orders that arrived early,
--   on time, or late versus the estimated delivery date?
-- Tables: olist.order_revenue, olist.orders, olist.order_reviews_clean.
-- Technique: order-level joins only (order_revenue and order_reviews_clean
--   are both one row per order, so there is no fan-out), CASE bucketing on
--   days late, aggregates per bucket.
-- Assumptions:
--   * days_late = delivered date minus estimated date, in whole days.
--     Negative means early. Most orders in this dataset arrive early because
--     the platform pads its estimates.
--   * Orders without a review or without a delivery timestamp are excluded;
--     the n_orders column shows how many orders each bucket keeps.
--   * This is an association between lateness and review scores. Nothing
--     here establishes causation.

WITH delay AS (
    SELECT r.order_id,
           CAST(o.order_delivered_customer_date AS date)
         - CAST(o.order_estimated_delivery_date AS date) AS days_late
    FROM olist.order_revenue r
    JOIN olist.orders o ON o.order_id = r.order_id
    WHERE o.order_delivered_customer_date IS NOT NULL
),

bucketed AS (
    SELECT d.order_id,
           CASE
               WHEN d.days_late <= -8 THEN '1. 8+ days early'
               WHEN d.days_late <= -1 THEN '2. 1-7 days early'
               WHEN d.days_late =   0 THEN '3. on time'
               WHEN d.days_late <=  3 THEN '4. 1-3 days late'
               WHEN d.days_late <=  7 THEN '5. 4-7 days late'
               ELSE                        '6. 8+ days late'
           END AS delivery_bucket,
           d.days_late
    FROM delay d
)

SELECT b.delivery_bucket,
       COUNT(*)                            AS n_orders,
       ROUND(AVG(b.days_late), 1)          AS avg_days_late,
       ROUND(AVG(rv.review_score), 2)      AS avg_review_score,
       -- Share of orders whose review is 1 star.
       ROUND(100.0 * AVG(CASE WHEN rv.review_score = 1 THEN 1 ELSE 0 END), 1)
           AS pct_one_star
FROM bucketed b
JOIN olist.order_reviews_clean rv ON rv.order_id = b.order_id
GROUP BY b.delivery_bucket
ORDER BY b.delivery_bucket;
