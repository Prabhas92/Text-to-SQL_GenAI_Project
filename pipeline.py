import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from answerer import summarize_answer
from executor import execute_sql
from generator import generate_sql
from guardrails import validate_sql
from schema import get_schema_context

# ============================================================
# pipeline.py
# The full Text-to-SQL flow:
#
#   question
#     -> generate SQL (LLM, structured output)
#     -> guardrails (deterministic)
#     -> execute (read-only)
#     -> on failure: send the error back to the LLM and retry
#     -> natural-language answer (LLM)
# ============================================================


PROJECT_DIR = Path(__file__).parent
DB_PATH = os.getenv("DB_PATH", str(PROJECT_DIR / "DB_Scripts" / "retail.db"))

# 1 first try + 2 self-correction retries.
MAX_ATTEMPTS = 3


@dataclass
class Attempt:
    sql: str
    error: str = ""

    # "guardrail" or "execution" — where it failed.
    stage: str = ""


@dataclass
class Answer:
    question: str

    # ok | unanswerable | failed
    status: str

    answer: str = ""
    sql: str = ""
    explanation: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    tables_read: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    total_tokens: int = 0
    latency_s: float = 0.0


class TextToSQL:

    def __init__(self, db_path=DB_PATH, summarize=True):
        self.db_path = db_path
        self.summarize = summarize

        # Read the schema once and reuse it for every question.
        self.schema_text, self.tables = get_schema_context(db_path)

    def ask(self, question, history=None):
        """
        Answer one question.

        history: list of {"question": ..., "sql": ...} from
                 earlier successful turns (for follow-ups).
        """

        start = time.perf_counter()
        out = Answer(question=question, status="failed")
        feedback = None

        for _ in range(MAX_ATTEMPTS):

            # ---- 1. Generate -----------------------------------
            result, usage = generate_sql(
                question, self.schema_text, history, feedback
            )
            out.total_tokens += usage.total_tokens
            out.explanation = result.explanation

            if not result.is_answerable:
                out.status = "unanswerable"
                out.answer = result.explanation
                break

            # ---- 2. Guardrails ---------------------------------
            guard = validate_sql(result.sql, self.db_path, self.tables)
            attempt = Attempt(sql=guard.sql)
            out.attempts.append(attempt)

            if not guard.ok:
                attempt.stage, attempt.error = "guardrail", guard.reason
                feedback = f"SQL:\n{guard.sql}\nRejected: {guard.reason}"
                continue

            # ---- 3. Execute ------------------------------------
            try:
                qr = execute_sql(guard.sql, self.db_path, self.tables)
            except sqlite3.Error as e:
                attempt.stage, attempt.error = "execution", str(e)
                feedback = f"SQL:\n{guard.sql}\nError: {e}"
                continue

            out.status = "ok"
            out.sql = guard.sql
            out.tables_read = guard.tables_read
            out.columns, out.rows = qr.columns, qr.rows
            out.truncated = qr.truncated
            break

        else:
            last = out.attempts[-1]
            out.answer = (
                f"Could not produce a valid query after "
                f"{MAX_ATTEMPTS} attempts. Last error: {last.error}"
            )

        # ---- 4. Natural-language answer ------------------------
        if out.status == "ok" and self.summarize:
            out.answer, usage = summarize_answer(
                question, out.sql, out.columns, out.rows, out.truncated
            )
            out.total_tokens += usage.total_tokens

        out.latency_s = time.perf_counter() - start
        return out


# -------------------------------------------------------------
# Interactive CLI:  python pipeline.py
# -------------------------------------------------------------
if __name__ == "__main__":

    bot = TextToSQL()
    history = []
    print(f"Text-to-SQL on {bot.db_path}. Tables: {bot.tables}")
    print("Ask a question (blank line to quit).\n")

    while True:
        q = input("❓ ").strip()
        if not q:
            break

        a = bot.ask(q, history)

        for i, att in enumerate(a.attempts, 1):
            if att.error:
                print(f"  ↻ attempt {i} failed ({att.stage}): {att.error}")
        if a.sql:
            print(f"\n{a.sql}\n")
            print(" | ".join(a.columns))
            for row in a.rows[:10]:
                print(" | ".join(str(v) for v in row))
            if len(a.rows) > 10:
                print(f"... {len(a.rows)} rows")
            history.append({"question": q, "sql": a.sql})

        print(f"\n💬 {a.answer}")
        print(f"   [{a.status} · {a.total_tokens} tokens · {a.latency_s:.1f}s]\n")
