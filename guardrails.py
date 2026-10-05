import re
import sqlite3
from dataclasses import dataclass, field

# ============================================================
# guardrails.py
# Deterministic checks that run on LLM-generated SQL BEFORE
# it is allowed anywhere near the real query execution.
#
# We never trust the model. Every query must pass:
#
#   1. Not empty
#   2. Exactly one statement
#   3. Starts with SELECT or WITH
#   4. No write / admin keywords (DELETE, DROP, PRAGMA, ...)
#   5. SQLite compiles it (EXPLAIN) and it only READS tables
#      on our allow-list (checked by SQLite's authorizer)
# ============================================================


# Keywords that must never appear in a read-only analytics query.
FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "REPLACE", "TRUNCATE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REINDEX", "ANALYZE", "GRANT", "REVOKE",
    "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE",
]


@dataclass
class GuardResult:

    # Did the query pass every check?
    ok: bool

    # Cleaned SQL (comments stripped, trailing ';' removed).
    sql: str

    # Why it was rejected (empty when ok).
    reason: str = ""

    # Real tables the query reads.
    tables_read: list[str] = field(default_factory=list)


# ------------------------------------------------------------
# 1. HELPERS
# ------------------------------------------------------------

def _strip_comments(sql):
    """Remove -- line comments and /* block */ comments."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def _mask_literals(sql):
    """
    Replace the contents of string literals and quoted
    identifiers with blanks.

    This stops false positives such as:

        WHERE status = 'delete; drop'

    from tripping the keyword and semicolon checks.
    """
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def _rootpage_map(conn):
    """
    Map every b-tree root page in the database to the table
    that owns it (an index maps to its parent table).

    Page 1 is sqlite_master itself.
    """
    pages = {1: "sqlite_master"}
    for tbl_name, rootpage in conn.execute(
        "SELECT tbl_name, rootpage FROM sqlite_master WHERE rootpage > 0"
    ):
        pages[rootpage] = tbl_name.lower()
    return pages


def make_authorizer(allowed_tables, real_tables):
    """
    Build a callback for sqlite3.Connection.set_authorizer().

    SQLite calls it for every action a statement wants to
    perform. We allow only SELECT itself, reads, function
    calls and recursive CTEs. Everything else (writes, PRAGMA,
    ATTACH, ...) is denied.

    Reads of real tables outside the allow-list (including
    sqlite_master) are denied. Reads of names that are not
    real tables are CTEs, which are allowed.
    """
    allowed = {t.lower() for t in allowed_tables}
    real = {t.lower() for t in real_tables}

    def authorizer(action, arg1, arg2, db_name, trigger):

        if action == sqlite3.SQLITE_READ:
            # arg1 = table (or CTE) name, arg2 = column name
            name = (arg1 or "").lower()
            if name in allowed:
                return sqlite3.SQLITE_OK
            if name in real or name.startswith("sqlite_"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        if action in (
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        ):
            return sqlite3.SQLITE_OK

        return sqlite3.SQLITE_DENY

    return authorizer


def connect_guarded(db_path, allowed_tables):
    """
    Open the database in SQLite read-only mode with the
    authorizer installed.

    Returns (conn, rootpage_map).
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    pages = _rootpage_map(conn)
    conn.set_authorizer(
        make_authorizer(allowed_tables, set(pages.values()))
    )
    return conn, pages


# ------------------------------------------------------------
# 2. MAIN ENTRY POINT
# ------------------------------------------------------------

def validate_sql(sql, db_path, allowed_tables):
    """
    Run every guardrail on `sql`.

    Returns a GuardResult. The caller should only execute
    result.sql when result.ok is True.
    """

    cleaned = _strip_comments(sql or "").strip()

    # Allow (and drop) a single trailing semicolon.
    cleaned = cleaned.rstrip().rstrip(";").strip()

    # Check 1: not empty
    if not cleaned:
        return GuardResult(False, cleaned, "Empty query.")

    masked = _mask_literals(cleaned)

    # Check 2: exactly one statement
    if ";" in masked:
        return GuardResult(
            False, cleaned,
            "Multiple statements are not allowed."
        )

    # Check 3: must be a SELECT (optionally with a CTE)
    first_word = masked.split(None, 1)[0].upper()
    if first_word not in ("SELECT", "WITH"):
        return GuardResult(
            False, cleaned,
            f"Only SELECT queries are allowed (got {first_word})."
        )

    # Check 4: forbidden keywords anywhere in the query
    upper = masked.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            return GuardResult(
                False, cleaned,
                f"Forbidden keyword: {kw}."
            )

    # Check 5: compile with EXPLAIN under the authorizer.
    #
    # EXPLAIN makes SQLite parse and plan the query without
    # running it. That catches syntax errors and unknown
    # columns, and the authorizer catches disallowed actions.
    conn, pages = connect_guarded(db_path, allowed_tables)
    try:
        program = conn.execute(f"EXPLAIN {cleaned}").fetchall()
    except sqlite3.DatabaseError as e:
        msg = str(e)
        if "not authorized" in msg or "prohibited" in msg:
            msg = (
                "Query touches a table or operation outside "
                f"the allow-list ({msg})."
            )
        return GuardResult(False, cleaned, msg)
    finally:
        conn.close()

    # Check 6: every table the compiled program opens must be
    # on the allow-list.
    #
    # The authorizer alone is not enough: SQLite does not
    # report columns used only in JOIN ... USING (...), so a
    # table could sneak in that way. Every table access needs
    # an OpenRead instruction whose p2 is the table's (or its
    # index's) root page, so this list is complete.
    #
    # EXPLAIN row: (addr, opcode, p1, p2, p3, p4, p5, comment)
    tables_read = {
        pages.get(row[3], f"rootpage {row[3]}")
        for row in program
        if row[1] in ("OpenRead", "ReopenIdx")
    }
    allowed = {t.lower() for t in allowed_tables}
    outside = sorted(tables_read - allowed)
    if outside:
        return GuardResult(
            False, cleaned,
            f"Query touches tables outside the allow-list: {outside}."
        )

    return GuardResult(True, cleaned, "", sorted(tables_read))


if __name__ == "__main__":

    from schema import get_schema_context

    db = "DB_Scripts/retail.db"
    _, tables = get_schema_context(db)

    for q in [
        "SELECT city, COUNT(*) FROM customers GROUP BY city;",
        "DELETE FROM orders",
        "SELECT 1; DROP TABLE customers",
        "SELECT * FROM sqlite_master",
        "SELECT nope FROM customers",
    ]:
        r = validate_sql(q, db, tables)
        print(f"{'PASS' if r.ok else 'BLOCK'}  {q}\n      {r.reason or r.tables_read}")
