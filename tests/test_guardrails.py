import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from executor import execute_sql  # noqa: E402
from guardrails import validate_sql  # noqa: E402

DB = str(ROOT / "DB_Scripts" / "retail.db")
TABLES = ["customers", "products", "orders", "order_items"]


@pytest.mark.parametrize("sql", [
    "SELECT city, COUNT(*) AS n FROM customers GROUP BY city ORDER BY n DESC",
    "select * from orders limit 5;",
    "WITH t AS (SELECT * FROM orders) SELECT status, COUNT(*) FROM t GROUP BY status",
    "SELECT * FROM orders WHERE status = 'delete; drop table x'",
    "-- top customers\nSELECT name FROM customers LIMIT 3",
    "SELECT o.order_id, SUM(oi.quantity * p.unit_price) AS revenue "
    "FROM orders o JOIN order_items oi ON o.order_id = oi.order_id "
    "JOIN products p ON p.product_id = oi.product_id GROUP BY o.order_id",
])
def test_allows_read_only_selects(sql):
    assert validate_sql(sql, DB, TABLES).ok


@pytest.mark.parametrize("sql, reason", [
    ("", "Empty"),
    ("DELETE FROM orders", "Only SELECT"),
    ("UPDATE products SET unit_price = 0", "Only SELECT"),
    ("DROP TABLE customers", "Only SELECT"),
    ("PRAGMA table_info(orders)", "Only SELECT"),
    ("ATTACH DATABASE 'x.db' AS x", "Only SELECT"),
    ("SELECT 1; DROP TABLE customers", "Multiple statements"),
    ("WITH x AS (SELECT 1) DELETE FROM orders", "Forbidden keyword"),
    ("SELECT * FROM sqlite_master", "allow-list"),
    ("SELECT * FROM employees", "no such table"),
    ("SELECT salary FROM customers", "no such column"),
])
def test_blocks_unsafe_or_invalid(sql, reason):
    r = validate_sql(sql, DB, TABLES)
    assert not r.ok
    assert reason in r.reason


def test_reports_tables_read():
    r = validate_sql(
        "SELECT c.city FROM customers c JOIN orders o USING (customer_id)",
        DB, TABLES,
    )
    assert r.tables_read == ["customers", "orders"]


def test_table_outside_allow_list_is_blocked():
    r = validate_sql("SELECT * FROM products", DB, ["customers"])
    assert not r.ok


def test_executor_truncates_rows():
    qr = execute_sql("SELECT * FROM orders", DB, TABLES, max_rows=10)
    assert len(qr.rows) == 10 and qr.truncated


def test_executor_is_read_only():
    with pytest.raises(sqlite3.Error):
        execute_sql("DELETE FROM orders", DB, TABLES)


def test_executor_times_out():
    slow = (
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
        "SELECT COUNT(*) FROM n"
    )
    with pytest.raises(sqlite3.OperationalError, match="time limit"):
        execute_sql(slow, DB, TABLES, timeout_s=0.5)


def test_using_join_cannot_bypass_allow_list():
    # SQLite's authorizer never sees USING-only columns, so this
    # is caught by inspecting the compiled program instead.
    r = validate_sql(
        "SELECT c.city FROM customers c JOIN orders USING (customer_id)",
        DB, ["customers"],
    )
    assert not r.ok and "orders" in r.reason


def test_recursive_cte_allowed():
    r = validate_sql(
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n LIMIT 12) "
        "SELECT i FROM n",
        DB, TABLES,
    )
    assert r.ok
