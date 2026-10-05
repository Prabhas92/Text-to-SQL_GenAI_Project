import sqlite3


def get_schema_context(db_path, sample_rows=3, max_distinct=10):
    """
    Read the SQLite database and create a text description
    that can later be given to the LLM.

    Returns:
        schema_text  -> description of tables, columns, sample data,
                        and allowed values
        table_names  -> list of actual table names
    """

    # ---------------------------------------------------------
    # 1. Connect to the database in READ-ONLY mode
    # ---------------------------------------------------------
    #
    # We are only inspecting the database.
    # We don't want schema.py to accidentally modify data.
    #
    conn = sqlite3.connect(
        f"file:{db_path}?mode=ro",
        uri=True
    )

    cur = conn.cursor()


    # ---------------------------------------------------------
    # 2. Find all user-created tables
    # ---------------------------------------------------------
    #
    # SQLite keeps metadata about tables in sqlite_master.
    #
    # We don't want SQLite's internal tables, so we exclude
    # anything whose name starts with "sqlite_".
    #
    tables = cur.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()


    # This list will contain the schema information
    # for every table.
    parts = []


    # ---------------------------------------------------------
    # 3. Process every table
    # ---------------------------------------------------------

    for name, ddl in tables:

        # Start the description with the CREATE TABLE statement.
        #
        # Example:
        #
        # CREATE TABLE customers (
        #     customer_id INTEGER PRIMARY KEY,
        #     name TEXT NOT NULL,
        #     city TEXT NOT NULL
        # );
        #
        block = [ddl + ";"]


        # -----------------------------------------------------
        # 4. Get a few sample rows
        # -----------------------------------------------------
        #
        # We don't need every row.
        # Three rows are enough to show the model what the
        # actual data looks like.
        #
        rows = cur.execute(
            f"SELECT * FROM {name} LIMIT {sample_rows}"
        ).fetchall()


        # cur.description contains metadata about the columns
        # returned by the SELECT statement.
        #
        # Example:
        #
        # [
        #     ('customer_id', ...),
        #     ('name', ...),
        #     ('city', ...)
        # ]
        #
        # We only need the first item from each tuple: the
        # column name.
        #
        columns = [d[0] for d in cur.description]


        # Add a heading showing the column names.
        block.append(
            f"-- sample rows ({', '.join(columns)}):"
        )


        # Add each sample row as a comment.
        #
        # Example:
        #
        # --   (1, 'Customer 1', 'Bengaluru')
        # --   (2, 'Customer 2', 'Delhi')
        #
        block.extend(
            f"--   {row}"
            for row in rows
        )


        # -----------------------------------------------------
        # 5. Find allowed values for short TEXT columns
        # -----------------------------------------------------
        #
        # PRAGMA table_info(table_name) gives us information
        # about every column in the table.
        #
        # We are particularly interested in TEXT columns.
        #
        for _, col, col_type, *_ in cur.execute(
            f"PRAGMA table_info({name})"
        ).fetchall():

            # Ignore columns that aren't TEXT.
            if col_type.upper() != "TEXT":
                continue


            # Count how many unique values exist in this column.
            #
            # Example:
            #
            # orders.status might contain:
            #
            # placed
            # shipped
            # delivered
            # cancelled
            # returned
            #
            # COUNT(DISTINCT status) would therefore return 5.
            #
            count = cur.execute(
                f"SELECT COUNT(DISTINCT {col}) FROM {name}"
            ).fetchone()[0]


            # Only list values when there are a small number
            # of distinct values.
            #
            # max_distinct = 10
            #
            # This prevents us from dumping thousands of
            # customer names into the LLM prompt.
            #
            if 0 < count <= max_distinct:

                values = [
                    r[0]
                    for r in cur.execute(
                        f"""
                        SELECT DISTINCT {col}
                        FROM {name}
                        ORDER BY 1
                        """
                    )
                ]


                # Add the real allowed values to the schema text.
                #
                # Example:
                #
                # -- allowed values for orders.status:
                # ['cancelled', 'delivered', 'placed',
                #  'returned', 'shipped']
                #
                block.append(
                    f"-- allowed values for {name}.{col}: {values}"
                )


        # Add this table's complete block to our collection.
        parts.append("\n".join(block))


    # ---------------------------------------------------------
    # 6. Close the database connection
    # ---------------------------------------------------------

    conn.close()


    # ---------------------------------------------------------
    # 7. Return the final schema context
    # ---------------------------------------------------------
    #
    # Each table is separated by two new lines.
    #
    return (
        "\n\n".join(parts),
        [name for name, _ in tables]
    )


# -------------------------------------------------------------
# 8. Run this file directly
# -------------------------------------------------------------
#
# When we execute:
#
#     python schema.py
#
# this section will run.
#
# It will inspect retail.db and print what the LLM would see.
#
if __name__ == "__main__":

    text, names = get_schema_context("DB_Scripts/retail.db")
    print(text)

    print("\nTables:", names)