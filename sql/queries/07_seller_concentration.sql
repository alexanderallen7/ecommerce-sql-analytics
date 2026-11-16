-- Question: How concentrated is revenue among sellers: what share of revenue
--   comes from the top 1, 5, and 20 percent of sellers?
-- Tables: olist.order_items, olist.order_revenue (as the delivered-in-window
--   filter), olist.sellers (implicitly via seller_id on items).
-- Technique: revenue per seller, then a cumulative window sum over sellers
--   ordered by revenue; each tier reads the cumulative sum at its cutoff rank.
-- Assumption: a seller's revenue is the sum of price + freight over their
--   item rows in delivered orders inside the analysis window, consistent
--   with the shared revenue definition.

WITH window_orders AS (
    SELECT order_id FROM olist.order_revenue
),

seller_revenue AS (
    SELECT oi.seller_id,
           SUM(oi.price + oi.freight_value) AS revenue
    FROM olist.order_items oi
    JOIN window_orders w ON w.order_id = oi.order_id
    GROUP BY oi.seller_id
),

ranked AS (
    SELECT seller_id,
           revenue,
           ROW_NUMBER() OVER (ORDER BY revenue DESC, seller_id) AS revenue_rank,
           COUNT(*) OVER ()  AS n_sellers,
           SUM(revenue) OVER (
               ORDER BY revenue DESC, seller_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS cumulative_revenue,
           SUM(revenue) OVER () AS total_revenue
    FROM seller_revenue
),

tiers (tier_label, tier_fraction) AS (
    VALUES ('Top 1%', 0.01), ('Top 5%', 0.05), ('Top 20%', 0.20)
)

SELECT t.tier_label,
       r.revenue_rank                                   AS sellers_in_tier,
       r.n_sellers                                      AS total_sellers,
       ROUND(r.cumulative_revenue, 2)                   AS tier_revenue,
       ROUND(100.0 * r.cumulative_revenue / r.total_revenue, 1)
                                                        AS pct_of_revenue
FROM tiers t
-- The row whose rank equals the tier cutoff carries the cumulative revenue
-- of every seller at or above the cutoff.
JOIN ranked r ON r.revenue_rank = CEIL(t.tier_fraction * r.n_sellers)
ORDER BY t.tier_fraction;
