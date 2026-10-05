import sqlite3
import time
from dataclasses import dataclass

from guardrails import connect_guarded

# ============================================================
# executor.py
# Runs a query that ALREADY passed guardrails.validate_sql().
#
# Defence in depth — even if a bad query slipped through:
#
#   - the connection is opened read-only (mode=ro)
#   - the same authorizer denies anything but table reads
#   - a progress handler aborts queries that run too long
#   - we fetch at most max_rows rows
# ============================================================


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]

    # True when the query returned more than max_rows rows.
    truncated: bool

    elapsed_ms: float


def execute_sql(
    sql,
    db_path,
    allowed_tables,
    max_rows=200,
    timeout_s=5.0,
):
    """
    Execute a validated SELECT and return a QueryResult.

    Raises sqlite3.Error on failure (the pipeline catches it
    and sends the message back to the LLM to self-correct).
    """

    conn, _ = connect_guarded(db_path, allowed_tables)

    # SQLite calls this every N virtual-machine steps.
    # Returning a truthy value interrupts the query.
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(
        lambda: time.monotonic() > deadline,
        10_000,
    )

    start = time.perf_counter()
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description]

        # Fetch one extra row so we know whether we truncated.
        rows = cur.fetchmany(max_rows + 1)

    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise sqlite3.OperationalError(
                f"Query exceeded the {timeout_s:.0f}s time limit."
            ) from e
        raise

    finally:
        conn.close()

    return QueryResult(
        columns=columns,
        rows=rows[:max_rows],
        truncated=len(rows) > max_rows,
        elapsed_ms=(time.perf_counter() - start) * 1000,
    )
