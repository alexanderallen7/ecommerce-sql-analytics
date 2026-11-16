-- Question: Which product categories earned the most revenue in each quarter?
-- Tables: olist.order_items, olist.products, olist.product_category_translation,
--   olist.order_revenue (as the filter for delivered orders in the window).
-- Technique: items aggregated to category-quarter level, RANK() within each
--   quarter, filtered to the top 3.
--   Choice of ranking function: RANK() shares a rank when two categories tie
--   on revenue and both are shown. DENSE_RANK() would also keep ties but
--   hides that a tie happened (no gap after it). ROW_NUMBER() would break the
--   tie arbitrarily and silently drop one of the tied categories. With
--   revenue summed to the cent, ties are unlikely, and RANK() handles them
--   correctly if they occur.
-- Assumptions:
--   * Category revenue allocates each item row (price + freight) to the
--     item's product category, so a multi-category order is split across its
--     categories.
--   * Categories are reported with their English names from the translation
--     table. Two categories have no translation and keep their Portuguese
--     names; 610 products have no category at all and are grouped as
--     'unknown'.

WITH window_orders AS (
    -- Delivered orders inside the analysis window, from the shared view.
    SELECT order_id, order_purchase_timestamp
    FROM olist.order_revenue
),

item_revenue AS (
    SELECT CAST(date_trunc('quarter', w.order_purchase_timestamp) AS date) AS quarter,
           COALESCE(t.product_category_name_english,
                    p.product_category_name,
                    'unknown') AS category,
           oi.price + oi.freight_value AS revenue
    FROM olist.order_items oi
    JOIN window_orders w ON w.order_id = oi.order_id
    JOIN olist.products p ON p.product_id = oi.product_id
    LEFT JOIN olist.product_category_translation t
           ON t.product_category_name = p.product_category_name
),

category_quarter AS (
    SELECT quarter,
           category,
           SUM(revenue) AS revenue,
           COUNT(*)     AS items_sold
    FROM item_revenue
    GROUP BY quarter, category
),

ranked AS (
    SELECT quarter,
           category,
           revenue,
           items_sold,
           RANK() OVER (PARTITION BY quarter ORDER BY revenue DESC) AS revenue_rank,
           -- Share of the whole quarter, computed before the top-3 filter.
           100.0 * revenue / SUM(revenue) OVER (PARTITION BY quarter) AS pct_of_quarter
    FROM category_quarter
)

SELECT quarter,
       revenue_rank,
       category,
       ROUND(revenue, 2)        AS revenue,
       items_sold,
       ROUND(pct_of_quarter, 1) AS pct_of_quarter
FROM ranked
WHERE revenue_rank <= 3
ORDER BY quarter, revenue_rank, category;
