-- Derived objects built on top of the raw tables. Every analysis query reads
-- from these instead of repeating filters or cleanup rules, so each rule is
-- defined exactly once.

-- -----------------------------------------------------------------------------
-- Analysis window: 2017-01-01 up to but not including 2018-09-01.
-- The dataset starts 2016-09 and ends 2018-10, but the edges are too sparse to
-- analyze (2016-09 has 4 orders, 2016-11 has none, 2016-12 has 1, 2018-09 has
-- 16, 2018-10 has 4). Every query that filters by date reads this one-row
-- table, so the window is applied consistently and changed in one place.
-- -----------------------------------------------------------------------------
CREATE TABLE olist.analysis_window AS
SELECT DATE '2017-01-01' AS window_start,
       DATE '2018-09-01' AS window_end_exclusive;

-- -----------------------------------------------------------------------------
-- Revenue definition, the single source of truth used by every query:
-- revenue of an order = SUM(price + freight_value) over its order_items rows,
-- for orders with status 'delivered', purchased inside the analysis window.
-- Items are aggregated to order level BEFORE any other join, so a query that
-- also touches payments or reviews cannot double count item rows.
-- Reconciliation against order_payments is checked in the test suite.
-- -----------------------------------------------------------------------------
CREATE VIEW olist.order_revenue AS
WITH items_per_order AS (
    SELECT order_id,
           SUM(price + freight_value) AS revenue,
           SUM(price)                 AS item_revenue,
           SUM(freight_value)         AS freight_revenue
    FROM olist.order_items
    GROUP BY order_id
)
SELECT o.order_id,
       o.customer_id,
       c.customer_unique_id,
       o.order_purchase_timestamp,
       CAST(date_trunc('month', o.order_purchase_timestamp) AS date) AS purchase_month,
       i.revenue,
       i.item_revenue,
       i.freight_revenue
FROM olist.orders o
JOIN items_per_order i  ON i.order_id = o.order_id
JOIN olist.customers c  ON c.customer_id = o.customer_id
CROSS JOIN olist.analysis_window w
WHERE o.order_status = 'delivered'
  AND o.order_purchase_timestamp >= w.window_start
  AND o.order_purchase_timestamp <  w.window_end_exclusive;

-- -----------------------------------------------------------------------------
-- One review per order. The raw table has 547 orders with more than one
-- review. Rule: keep the review the customer answered last
-- (latest review_answer_timestamp), tie-broken by latest review_creation_date,
-- then by review_id so the result is deterministic.
-- -----------------------------------------------------------------------------
CREATE VIEW olist.order_reviews_clean AS
SELECT review_id,
       order_id,
       review_score,
       review_creation_date,
       review_answer_timestamp
FROM (
    SELECT r.*,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY review_answer_timestamp DESC,
                        review_creation_date DESC,
                        review_id DESC
           ) AS rn
    FROM olist.order_reviews r
) ranked
WHERE rn = 1;

-- -----------------------------------------------------------------------------
-- Geolocation deduplicated to one row per zip prefix. Rule: average the
-- coordinates, take the most frequent city and state. MODE() WITHIN GROUP is
-- Postgres-specific syntax. Materialized as a table because it aggregates a
-- million rows. Every join goes through this table; the raw one stays
-- unjoined.
-- -----------------------------------------------------------------------------
CREATE TABLE olist.geolocation_prefix AS
SELECT geolocation_zip_code_prefix AS zip_code_prefix,
       AVG(geolocation_lat)  AS lat,
       AVG(geolocation_lng)  AS lng,
       MODE() WITHIN GROUP (ORDER BY geolocation_city)  AS city,
       MODE() WITHIN GROUP (ORDER BY geolocation_state) AS state
FROM olist.geolocation
GROUP BY geolocation_zip_code_prefix;

ALTER TABLE olist.geolocation_prefix ADD PRIMARY KEY (zip_code_prefix);
