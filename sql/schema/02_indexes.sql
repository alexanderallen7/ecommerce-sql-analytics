-- Indexes on foreign keys and on the timestamp columns the queries filter
-- or window over. Created after the bulk load so the load stays fast.

CREATE INDEX idx_customers_unique_id      ON olist.customers (customer_unique_id);
CREATE INDEX idx_orders_purchase_ts       ON olist.orders (order_purchase_timestamp);
CREATE INDEX idx_orders_status            ON olist.orders (order_status);
CREATE INDEX idx_orders_delivered_ts      ON olist.orders (order_delivered_customer_date);
CREATE INDEX idx_order_items_product_id   ON olist.order_items (product_id);
CREATE INDEX idx_order_items_seller_id    ON olist.order_items (seller_id);
CREATE INDEX idx_order_reviews_order_id   ON olist.order_reviews (order_id);
CREATE INDEX idx_geolocation_zip_prefix   ON olist.geolocation (geolocation_zip_code_prefix);
-- order_payments.order_id and order_items.order_id are the leading columns
-- of their primary keys, so they need no extra index.
