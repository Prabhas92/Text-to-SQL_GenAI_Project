import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import TextToSQL  # noqa: E402

# ============================================================
# run_eval.py
# Execution-accuracy evaluation.
#
#   python evals/run_eval.py
#
# For every question in golden.json we run the pipeline and
# compare its RESULT (not its SQL text) with the gold SQL's
# result. Two queries can look different and still be right.
#
# Match rule: every column of the gold result must appear in
# the predicted result with the same values (order-insensitive,
# floats rounded to 2 decimals). Extra predicted columns
# (e.g. a revenue column next to the product name) are fine.
# ============================================================


def _column_values(rows, i):
    vals = [round(r[i], 2) if isinstance(r[i], float) else r[i] for r in rows]
    return sorted(vals, key=repr)


def results_match(gold_rows, pred_cols_rows):
    pred_rows = pred_cols_rows
    if len(gold_rows) != len(pred_rows):
        return False
    if not gold_rows:
        return True

    pred_columns = [
        _column_values(pred_rows, j) for j in range(len(pred_rows[0]))
    ]
    return all(
        _column_values(gold_rows, i) in pred_columns
        for i in range(len(gold_rows[0]))
    )


def main():
    cases = json.loads((Path(__file__).parent / "golden.json").read_text())

    # Skip the answer-summary LLM call: we only grade the SQL.
    bot = TextToSQL(summarize=False)
    conn = sqlite3.connect(f"file:{bot.db_path}?mode=ro", uri=True)

    passed, tokens, retries = 0, 0, 0
    failures = []

    for case in cases:
        q = case["question"]
        a = bot.ask(q)
        tokens += a.total_tokens
        retries += max(0, len(a.attempts) - 1)

        if case.get("expect_unanswerable"):
            ok = a.status == "unanswerable"
        else:
            gold = conn.execute(case["gold_sql"]).fetchall()
            ok = a.status == "ok" and results_match(gold, a.rows)

        passed += ok
        mark = "✅" if ok else "❌"
        print(f"{mark} {q}  [{a.status}, {a.latency_s:.1f}s]")
        if not ok:
            failures.append((q, a))

    n = len(cases)
    print(
        f"\nExecution accuracy: {passed}/{n} = {passed / n:.0%}"
        f" · self-correction retries: {retries}"
        f" · total tokens: {tokens}"
    )

    for q, a in failures:
        print(f"\n--- FAILED: {q}\n{a.sql or a.answer}")

    return 0 if passed == n else 1


if __name__ == "__main__":
    sys.exit(main())
