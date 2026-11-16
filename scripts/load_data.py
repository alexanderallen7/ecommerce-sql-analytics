"""Build and fill the database from the raw CSVs.

Drops and recreates the olist schema, bulk loads the nine CSVs with COPY,
then creates indexes and derived views. Safe to run repeatedly: every run
rebuilds the schema from scratch and produces the same database.

Usage: python scripts/load_data.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import PROJECT_ROOT, SQL_DIR, get_connection, run_sql_file

RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Load order respects foreign keys: parents before children.
TABLES = [
    ("olist.customers", "olist_customers_dataset.csv"),
    ("olist.products", "olist_products_dataset.csv"),
    ("olist.sellers", "olist_sellers_dataset.csv"),
    ("olist.orders", "olist_orders_dataset.csv"),
    ("olist.order_items", "olist_order_items_dataset.csv"),
    ("olist.order_payments", "olist_order_payments_dataset.csv"),
    ("olist.order_reviews", "olist_order_reviews_dataset.csv"),
    ("olist.geolocation", "olist_geolocation_dataset.csv"),
    ("olist.product_category_translation", "product_category_name_translation.csv"),
]


def check_raw_files() -> None:
    missing = [csv for _, csv in TABLES if not (RAW_DIR / csv).exists()]
    if missing:
        print("Missing CSVs in data/raw/:")
        for name in missing:
            print(f"  {name}")
        print(
            "Download the Olist dataset from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce "
            "and unzip it into data/raw/."
        )
        sys.exit(1)


def copy_csv(conn, table: str, csv_path: Path) -> int:
    """Bulk load one CSV with COPY. Column order in the CSVs matches the DDL."""
    with conn.cursor() as cur:
        with open(csv_path, "rb") as f:
            with cur.copy(
                f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)"
            ) as copy:
                while chunk := f.read(1 << 20):
                    copy.write(chunk)
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]


def main() -> None:
    check_raw_files()
    started = time.time()
    with get_connection() as conn:
        print("Creating schema (drop + recreate) ...")
        run_sql_file(conn, SQL_DIR / "schema" / "01_tables.sql")
        for table, csv_name in TABLES:
            n = copy_csv(conn, table, RAW_DIR / csv_name)
            print(f"  {table}: {n:,} rows")
        print("Creating indexes ...")
        run_sql_file(conn, SQL_DIR / "schema" / "02_indexes.sql")
        print("Creating derived views and tables ...")
        run_sql_file(conn, SQL_DIR / "schema" / "03_derived.sql")
        conn.execute("ANALYZE")
        conn.commit()
    print(f"Done in {time.time() - started:.1f}s")


if __name__ == "__main__":
    main()
