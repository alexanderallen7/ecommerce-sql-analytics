-- Table definitions for the Olist e-commerce dataset.
-- The whole schema is dropped and recreated on every load, which makes the
-- load idempotent: running it twice gives the same database.
--
-- Typing notes:
--   * Zip code prefixes keep leading zeros in the CSVs ("01037"), so they are
--     TEXT. An integer type would silently drop the zeros.
--   * Monetary values are NUMERIC(10,2). Coordinates are DOUBLE PRECISION.
--   * Four product columns are misspelled in the source CSVs
--     (product_name_lenght etc.). They are renamed to the correct spelling
--     here; the load maps CSV columns to table columns by position.
--
-- Constraint notes, based on profiling the raw files:
--   * customers.customer_id is unique per order, so orders.customer_id gets
--     both a FK and a UNIQUE constraint. The person is customer_unique_id,
--     which repeats across orders and is indexed without a unique constraint.
--   * order_reviews: review_id alone is NOT unique in the data (814 duplicate
--     rows) and 547 orders have more than one review. The pair
--     (review_id, order_id) is unique and is the primary key. A clean
--     one-row-per-order view is defined in 03_derived.sql.
--   * geolocation has ~1,000,163 rows across 19,015 zip prefixes, so it has
--     no primary key as delivered. It is loaded raw and deduplicated into
--     geolocation_prefix in 03_derived.sql. Nothing joins to the raw table.

DROP SCHEMA IF EXISTS olist CASCADE;
CREATE SCHEMA olist;

CREATE TABLE olist.customers (
    customer_id              TEXT PRIMARY KEY,
    customer_unique_id       TEXT NOT NULL,
    customer_zip_code_prefix TEXT NOT NULL,
    customer_city            TEXT NOT NULL,
    customer_state           TEXT NOT NULL
);

CREATE TABLE olist.orders (
    order_id                      TEXT PRIMARY KEY,
    customer_id                   TEXT NOT NULL UNIQUE REFERENCES olist.customers (customer_id),
    order_status                  TEXT NOT NULL,
    order_purchase_timestamp      TIMESTAMP NOT NULL,
    order_approved_at             TIMESTAMP,
    order_delivered_carrier_date  TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP NOT NULL
);

CREATE TABLE olist.products (
    product_id                 TEXT PRIMARY KEY,
    product_category_name      TEXT,
    product_name_length        INTEGER,
    product_description_length INTEGER,
    product_photos_qty         INTEGER,
    product_weight_g           INTEGER,
    product_length_cm          INTEGER,
    product_height_cm          INTEGER,
    product_width_cm           INTEGER
);

CREATE TABLE olist.sellers (
    seller_id              TEXT PRIMARY KEY,
    seller_zip_code_prefix TEXT NOT NULL,
    seller_city            TEXT NOT NULL,
    seller_state           TEXT NOT NULL
);

CREATE TABLE olist.order_items (
    order_id            TEXT NOT NULL REFERENCES olist.orders (order_id),
    order_item_id       INTEGER NOT NULL,
    product_id          TEXT NOT NULL REFERENCES olist.products (product_id),
    seller_id           TEXT NOT NULL REFERENCES olist.sellers (seller_id),
    shipping_limit_date TIMESTAMP NOT NULL,
    price               NUMERIC(10, 2) NOT NULL,
    freight_value       NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE olist.order_payments (
    order_id             TEXT NOT NULL REFERENCES olist.orders (order_id),
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value        NUMERIC(10, 2) NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE olist.order_reviews (
    review_id               TEXT NOT NULL,
    order_id                TEXT NOT NULL REFERENCES olist.orders (order_id),
    review_score            INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TIMESTAMP NOT NULL,
    review_answer_timestamp TIMESTAMP NOT NULL,
    PRIMARY KEY (review_id, order_id)
);

-- Raw geolocation: no key, see header comment.
CREATE TABLE olist.geolocation (
    geolocation_zip_code_prefix TEXT NOT NULL,
    geolocation_lat             DOUBLE PRECISION NOT NULL,
    geolocation_lng             DOUBLE PRECISION NOT NULL,
    geolocation_city            TEXT NOT NULL,
    geolocation_state           TEXT NOT NULL
);

CREATE TABLE olist.product_category_translation (
    product_category_name         TEXT PRIMARY KEY,
    product_category_name_english TEXT NOT NULL
);
