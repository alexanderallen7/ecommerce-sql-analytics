import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import get_connection


@pytest.fixture(scope="session")
def conn():
    with get_connection() as c:
        yield c
        c.rollback()


def one(conn, sql, params=None):
    """Run a query and return the single value of its single row."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return row[0]
