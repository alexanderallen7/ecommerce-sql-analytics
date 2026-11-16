"""Correctness and reconciliation tests for the analysis queries.

Correctness: retention, RFM, and rolling revenue run against a small
hand-made fixture dataset in a separate schema, where the right answer was
worked out by hand. The production query text is reused unchanged except
that the schema name is swapped, so the logic under test is identical.

Reconciliation: on the real data, totals from different queries must agree
with each other and with the shared revenue definition.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from conftest import one
from src.db import read_sql_file

QUERIES = Path(__file__).resolve().parent.parent / "sql" / "queries"


def run_query(conn, name, schema="olist"):
    sql = read_sql_file(QUERIES / name)
    if schema != "olist":
        sql = sql.replace("olist.", f"{schema}.")
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    return cols, rows


# ---------------------------------------------------------------------------
# Fixture dataset. fixture.order_revenue mirrors the columns of the
# production view that the three queries under test read.
# ---------------------------------------------------------------------------

FIXTURE_SQL = """
DROP SCHEMA IF EXISTS fixture CASCADE;
CREATE SCHEMA fixture;

CREATE TABLE fixture.analysis_window AS
SELECT DATE '2021-01-01' AS window_start,
       DATE '2021-02-05' AS window_end_exclusive;

CREATE TABLE fixture.order_revenue (
    order_id                 TEXT,
    customer_unique_id       TEXT,
    order_purchase_timestamp TIMESTAMP,
    purchase_month           DATE,
    revenue                  NUMERIC(10, 2)
);

INSERT INTO fixture.order_revenue VALUES
    -- Rolling-revenue cases (customers X/Y, see test_rolling_fixture):
    -- one order on day 1, two orders on day 3 (their revenues must be
    -- summed into one day), one order on day 34.
    ('o1', 'X', '2021-01-01 10:00', '2021-01-01', 10),
    ('o2', 'X', '2021-01-03 09:00', '2021-01-01', 12),
    ('o3', 'Y', '2021-01-03 15:00', '2021-01-01',  8),
    ('o4', 'Y', '2021-02-03 12:00', '2021-02-01',  5);
"""

# A separate, bigger fixture for retention and RFM, with a 4-month window.
FIXTURE_RFM_SQL = """
DROP SCHEMA IF EXISTS fixture CASCADE;
CREATE SCHEMA fixture;

CREATE TABLE fixture.analysis_window AS
SELECT DATE '2021-01-01' AS window_start,
       DATE '2021-05-01' AS window_end_exclusive;

CREATE TABLE fixture.order_revenue (
    order_id                 TEXT,
    customer_unique_id       TEXT,
    order_purchase_timestamp TIMESTAMP,
    purchase_month           DATE,
    revenue                  NUMERIC(10, 2)
);

INSERT INTO fixture.order_revenue VALUES
    -- P, Q, R, S buy once with distinct recency and spend, so the five
    -- NTILE(5) quintiles over five customers are one customer each.
    ('p1', 'P', '2021-04-25 10:00', '2021-04-01', 500),
    ('q1', 'Q', '2021-04-10 10:00', '2021-04-01', 400),
    ('r1', 'R', '2021-03-01 10:00', '2021-03-01', 300),
    ('s1', 'S', '2021-02-01 10:00', '2021-02-01', 200),
    -- T buys twice in January (frequency 2).
    ('t1', 'T', '2021-01-05 10:00', '2021-01-01', 100),
    ('t2', 'T', '2021-01-10 10:00', '2021-01-01',  50);
"""

# Retention fixture: two cohorts whose grid can be enumerated by hand.
FIXTURE_RETENTION_SQL = """
DROP SCHEMA IF EXISTS fixture CASCADE;
CREATE SCHEMA fixture;

CREATE TABLE fixture.analysis_window AS
SELECT DATE '2021-01-01' AS window_start,
       DATE '2021-05-01' AS window_end_exclusive;

CREATE TABLE fixture.order_revenue (
    order_id                 TEXT,
    customer_unique_id       TEXT,
    order_purchase_timestamp TIMESTAMP,
    purchase_month           DATE,
    revenue                  NUMERIC(10, 2)
);

INSERT INTO fixture.order_revenue VALUES
    -- A: first buys January, returns March (offset 2).
    ('a1', 'A', '2021-01-10 10:00', '2021-01-01', 10),
    ('a2', 'A', '2021-03-05 10:00', '2021-03-01', 20),
    -- B: buys January only.
    ('b1', 'B', '2021-01-20 10:00', '2021-01-01', 30),
    -- C: two February orders (same-month repeat counts once at offset 0),
    -- returns April (offset 2).
    ('c1', 'C', '2021-02-15 10:00', '2021-02-01', 40),
    ('c2', 'C', '2021-02-20 10:00', '2021-02-01', 15),
    ('c3', 'C', '2021-04-01 10:00', '2021-04-01', 25);
"""


@pytest.fixture
def fixture_schema(conn):
    def build(sql):
        conn.execute(sql)
        conn.commit()

    yield build
    conn.execute("DROP SCHEMA IF EXISTS fixture CASCADE")
    conn.commit()


# ---------------------------------------------------------------------------
# Correctness against hand-computed fixtures
# ---------------------------------------------------------------------------

def test_retention_fixture(conn, fixture_schema):
    import datetime

    fixture_schema(FIXTURE_RETENTION_SQL)
    cols, rows = run_query(conn, "02_cohort_retention.sql", schema="fixture")
    d = datetime.date
    # (cohort_month, cohort_size, month_offset, active, retention_pct)
    expected = [
        (d(2021, 1, 1), 2, 0, 2, Decimal("100.00")),
        (d(2021, 1, 1), 2, 1, 0, Decimal("0.00")),
        (d(2021, 1, 1), 2, 2, 1, Decimal("50.00")),   # A returned in March
        (d(2021, 1, 1), 2, 3, 0, Decimal("0.00")),
        (d(2021, 2, 1), 1, 0, 1, Decimal("100.00")),  # C's repeat in Feb counts once
        (d(2021, 2, 1), 1, 1, 0, Decimal("0.00")),
        (d(2021, 2, 1), 1, 2, 1, Decimal("100.00")),  # C returned in April
        (d(2021, 2, 1), 1, 3, None, None),            # May is outside the window
    ]
    assert rows == expected


def test_rfm_fixture(conn, fixture_schema):
    fixture_schema(FIXTURE_RFM_SQL)
    cols, rows = run_query(conn, "03_rfm_segmentation.sql", schema="fixture")
    # Hand-derived scores (reference date 2021-05-01):
    #   P: recency 6,  freq 1, monetary 500 -> r5 m5 f1 -> Recent high value
    #   Q: recency 21, freq 1, monetary 400 -> r4 m4 f1 -> Recent high value
    #   R: recency 61, freq 1, monetary 300 -> r3 m3 f1 -> Middle
    #   S: recency 89, freq 1, monetary 200 -> r2 m2 f1 -> Lapsed low value
    #   T: recency 111, freq 2, monetary 150 -> r1 m1 f2 -> Lapsed repeat
    # Total revenue 1550. Output is ordered by segment revenue descending.
    expected = [
        ("Recent high value", 2, Decimal("40.0"), Decimal("900.00"),
         Decimal("58.1"), Decimal("14"), Decimal("1.00"), Decimal("450.00")),
        ("Middle", 1, Decimal("20.0"), Decimal("300.00"),
         Decimal("19.4"), Decimal("61"), Decimal("1.00"), Decimal("300.00")),
        ("Lapsed low value", 1, Decimal("20.0"), Decimal("200.00"),
         Decimal("12.9"), Decimal("89"), Decimal("1.00"), Decimal("200.00")),
        ("Lapsed repeat", 1, Decimal("20.0"), Decimal("150.00"),
         Decimal("9.7"), Decimal("111"), Decimal("2.00"), Decimal("150.00")),
    ]
    assert rows == expected


def test_rolling_fixture(conn, fixture_schema):
    import datetime

    fixture_schema(FIXTURE_SQL)
    cols, rows = run_query(conn, "04_rolling_revenue.sql", schema="fixture")
    d = datetime.date
    # 35-day spine: 2021-01-01 .. 2021-02-04.
    assert len(rows) == 35
    by_day = {r[0]: r for r in rows}

    def check(day, revenue, rolling, cumulative, complete):
        r = by_day[day]
        assert r[1] == Decimal(revenue)
        assert r[2] == Decimal(rolling)
        assert r[3] == Decimal(cumulative)
        assert r[4] is complete

    check(d(2021, 1, 1), "10.00", "10.00", "10.00", False)   # first order
    check(d(2021, 1, 2), "0.00", "10.00", "10.00", False)    # gap day appears
    check(d(2021, 1, 3), "20.00", "30.00", "30.00", False)   # two orders summed
    check(d(2021, 1, 30), "0.00", "30.00", "30.00", True)    # first full window
    check(d(2021, 1, 31), "0.00", "20.00", "30.00", True)    # Jan 1 drops out
    check(d(2021, 2, 1), "0.00", "20.00", "30.00", True)     # Jan 3 still in
    check(d(2021, 2, 2), "0.00", "0.00", "30.00", True)      # Jan 3 dropped out
    check(d(2021, 2, 3), "5.00", "5.00", "35.00", True)
    check(d(2021, 2, 4), "0.00", "5.00", "35.00", True)
    assert rows[-1][3] == Decimal("35.00")                   # cumulative = total


# ---------------------------------------------------------------------------
# Reconciliation on the real data
# ---------------------------------------------------------------------------

def total_revenue(conn):
    return one(conn, "SELECT ROUND(SUM(revenue), 2) FROM olist.order_revenue")


def total_customers(conn):
    return one(conn, "SELECT COUNT(DISTINCT customer_unique_id) FROM olist.order_revenue")


def test_monthly_revenue_sums_to_total(conn):
    cols, rows = run_query(conn, "01_monthly_revenue_trend.sql")
    i = cols.index("revenue")
    assert sum(r[i] for r in rows) == total_revenue(conn)


def test_monthly_orders_sum_to_total(conn):
    cols, rows = run_query(conn, "01_monthly_revenue_trend.sql")
    i = cols.index("order_count")
    assert sum(r[i] for r in rows) == one(
        conn, "SELECT COUNT(*) FROM olist.order_revenue"
    )


def test_cohort_sizes_sum_to_distinct_customers(conn):
    cols, rows = run_query(conn, "02_cohort_retention.sql")
    i_offset = cols.index("month_offset")
    i_size = cols.index("cohort_size")
    sizes = sum(r[i_size] for r in rows if r[i_offset] == 0)
    assert sizes == total_customers(conn)


def test_cohort_offset_zero_is_100_pct(conn):
    cols, rows = run_query(conn, "02_cohort_retention.sql")
    i_offset = cols.index("month_offset")
    i_pct = cols.index("retention_pct")
    assert all(
        r[i_pct] == Decimal("100.00") for r in rows if r[i_offset] == 0
    )


def test_rfm_segment_counts_sum_to_customers(conn):
    cols, rows = run_query(conn, "03_rfm_segmentation.sql")
    i = cols.index("customers")
    assert sum(r[i] for r in rows) == total_customers(conn)


def test_rfm_segment_revenue_sums_to_total(conn):
    cols, rows = run_query(conn, "03_rfm_segmentation.sql")
    i = cols.index("revenue")
    # Segment revenues are rounded to cents, so allow a cent per segment.
    assert abs(sum(r[i] for r in rows) - total_revenue(conn)) <= Decimal("0.07")


def test_cumulative_revenue_ends_at_total(conn):
    cols, rows = run_query(conn, "04_rolling_revenue.sql")
    i = cols.index("cumulative_revenue")
    assert rows[-1][i] == total_revenue(conn)


def test_rolling_spine_has_every_day(conn):
    cols, rows = run_query(conn, "04_rolling_revenue.sql")
    assert len(rows) == 608  # 2017-01-01 .. 2018-08-31 inclusive


def test_seller_tiers_are_nested(conn):
    cols, rows = run_query(conn, "07_seller_concentration.sql")
    i = cols.index("pct_of_revenue")
    pcts = [r[i] for r in rows]
    assert pcts == sorted(pcts)
    assert all(Decimal("0") < p <= Decimal("100") for p in pcts)


def test_delivery_buckets_cover_reviewed_delivered_orders(conn):
    cols, rows = run_query(conn, "06_delivery_delay_reviews.sql")
    i = cols.index("n_orders")
    expected = one(
        conn,
        """
        SELECT COUNT(*)
        FROM olist.order_revenue r
        JOIN olist.orders o ON o.order_id = r.order_id
        JOIN olist.order_reviews_clean rv ON rv.order_id = r.order_id
        WHERE o.order_delivered_customer_date IS NOT NULL
        """,
    )
    assert sum(r[i] for r in rows) == expected
