"""Data quality checks that run against the loaded Docker database.

Covers: row counts match the raw CSVs, primary keys are unique, no orphaned
foreign keys, timestamps fall in a plausible range, and the documented facts
about the dataset (duplicate review_ids, one customer_id per order) hold.
"""

import csv
from pathlib import Path

import pytest

from conftest import one

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

EXPECTED = [
    ("olist.customers", "olist_customers_dataset.csv"),
    ("olist.orders", "olist_orders_dataset.csv"),
    ("olist.order_items", "olist_order_items_dataset.csv"),
    ("olist.order_payments", "olist_order_payments_dataset.csv"),
    ("olist.order_reviews", "olist_order_reviews_dataset.csv"),
    ("olist.products", "olist_products_dataset.csv"),
    ("olist.sellers", "olist_sellers_dataset.csv"),
    ("olist.geolocation", "olist_geolocation_dataset.csv"),
    ("olist.product_category_translation", "product_category_name_translation.csv"),
]


def csv_row_count(path: Path) -> int:
    # csv.reader handles quoted fields with embedded newlines (review texts),
    # so this counts records correctly even when a field spans lines.
    with open(path, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.reader(f)) - 1  # minus header


@pytest.mark.parametrize("table,csv_name", EXPECTED)
def test_row_counts_match_csv(conn, table, csv_name):
    assert one(conn, f"SELECT COUNT(*) FROM {table}") == csv_row_count(RAW / csv_name)


@pytest.mark.parametrize(
    "table,key_cols",
    [
        ("olist.customers", "customer_id"),
        ("olist.orders", "order_id"),
        ("olist.products", "product_id"),
        ("olist.sellers", "seller_id"),
        ("olist.order_items", "order_id, order_item_id"),
        ("olist.order_payments", "order_id, payment_sequential"),
        ("olist.order_reviews", "review_id, order_id"),
        ("olist.product_category_translation", "product_category_name"),
        ("olist.geolocation_prefix", "zip_code_prefix"),
    ],
)
def test_primary_keys_unique(conn, table, key_cols):
    dupes = one(
        conn,
        f"SELECT COUNT(*) FROM (SELECT {key_cols} FROM {table} "
        f"GROUP BY {key_cols} HAVING COUNT(*) > 1) d",
    )
    assert dupes == 0


@pytest.mark.parametrize(
    "child,child_col,parent,parent_col",
    [
        ("olist.orders", "customer_id", "olist.customers", "customer_id"),
        ("olist.order_items", "order_id", "olist.orders", "order_id"),
        ("olist.order_items", "product_id", "olist.products", "product_id"),
        ("olist.order_items", "seller_id", "olist.sellers", "seller_id"),
        ("olist.order_payments", "order_id", "olist.orders", "order_id"),
        ("olist.order_reviews", "order_id", "olist.orders", "order_id"),
    ],
)
def test_no_orphaned_foreign_keys(conn, child, child_col, parent, parent_col):
    orphans = one(
        conn,
        f"SELECT COUNT(*) FROM {child} c LEFT JOIN {parent} p "
        f"ON c.{child_col} = p.{parent_col} WHERE p.{parent_col} IS NULL",
    )
    assert orphans == 0


def test_purchase_timestamps_plausible(conn):
    out_of_range = one(
        conn,
        """
        SELECT COUNT(*) FROM olist.orders
        WHERE order_purchase_timestamp < TIMESTAMP '2016-09-01'
           OR order_purchase_timestamp > TIMESTAMP '2018-11-01'
        """,
    )
    assert out_of_range == 0


def test_delivery_dates_not_before_purchase(conn):
    # Sanity check on timestamp ordering for delivered orders.
    bad = one(
        conn,
        """
        SELECT COUNT(*) FROM olist.orders
        WHERE order_delivered_customer_date IS NOT NULL
          AND order_delivered_customer_date < order_purchase_timestamp
        """,
    )
    assert bad == 0


def test_customer_id_is_one_per_order(conn):
    # The documented trap: customer_id is an order-level key.
    assert one(conn, "SELECT COUNT(*) FROM olist.orders") == one(
        conn, "SELECT COUNT(DISTINCT customer_id) FROM olist.orders"
    )
    # The person-level key repeats.
    assert one(conn, "SELECT COUNT(DISTINCT customer_unique_id) FROM olist.customers") < one(
        conn, "SELECT COUNT(*) FROM olist.customers"
    )


def test_raw_reviews_have_duplicate_review_ids(conn):
    # Documents why (review_id, order_id) is the primary key.
    assert one(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT review_id FROM olist.order_reviews
            GROUP BY review_id HAVING COUNT(*) > 1
        ) d
        """,
    ) > 0


def test_reviews_clean_is_one_row_per_order(conn):
    assert one(conn, "SELECT COUNT(*) FROM olist.order_reviews_clean") == one(
        conn, "SELECT COUNT(DISTINCT order_id) FROM olist.order_reviews"
    )


def test_order_revenue_is_one_row_per_order(conn):
    assert one(conn, "SELECT COUNT(*) FROM olist.order_revenue") == one(
        conn, "SELECT COUNT(DISTINCT order_id) FROM olist.order_revenue"
    )


def test_revenue_positive(conn):
    assert one(conn, "SELECT COUNT(*) FROM olist.order_revenue WHERE revenue <= 0") == 0


def test_revenue_reconciles_with_payments(conn):
    """Item revenue (price + freight) vs payment totals for the same orders.

    The two are recorded independently (vouchers, rounding of installments),
    so they will not match to the cent. The gap measured on the full delivered
    set is 0.017 percent; the test allows 0.1 percent.
    """
    gap_pct = one(
        conn,
        """
        WITH pay AS (
            SELECT order_id, SUM(payment_value) AS paid
            FROM olist.order_payments
            GROUP BY order_id
        )
        SELECT ABS(SUM(p.paid) - SUM(r.revenue)) / SUM(r.revenue) * 100
        FROM olist.order_revenue r
        JOIN pay p ON p.order_id = r.order_id
        """,
    )
    assert float(gap_pct) < 0.1
