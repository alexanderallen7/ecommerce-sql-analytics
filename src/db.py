"""Database connection and SQL file helpers.

Python's role in this project is plumbing: open a connection, run .sql files,
hand query results to pandas for charting. The analysis itself lives in SQL.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"

load_dotenv(PROJECT_ROOT / ".env")


def connection_string() -> str:
    return (
        f"host={os.environ['POSTGRES_HOST']} "
        f"port={os.environ['POSTGRES_PORT']} "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


def get_connection() -> psycopg.Connection:
    return psycopg.connect(connection_string())


def read_sql_file(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    """Execute a .sql file as a single script."""
    conn.execute(read_sql_file(path))


def fetch_sql_file(conn: psycopg.Connection, path: Path):
    """Run a query file and return (column_names, rows)."""
    with conn.cursor() as cur:
        cur.execute(read_sql_file(path))
        columns = [d.name for d in cur.description]
        rows = cur.fetchall()
    return columns, rows
