from generator import MODEL, client

# ============================================================
# answerer.py
# Turns the raw result rows into a short natural-language
# answer for a business user.
# ============================================================


ANSWER_PROMPT = """
You explain SQL query results to a business user.

Rules:

- Answer the user's question in 1-3 short sentences.
- Use ONLY the numbers and values in the result rows.
  Never invent or estimate numbers.
- Amounts are in Indian Rupees: format money as ₹ with 2 decimals
  and thousands separators.
- If the result is empty, say no matching data was found.
- If the rows were truncated, mention that only the first rows
  are shown.
"""


def summarize_answer(question, sql, columns, rows, truncated, max_rows=30):
    """
    Return (answer_text, usage).

    Only the first `max_rows` rows are sent to the LLM to keep
    the prompt small.
    """

    preview = "\n".join(str(r) for r in rows[:max_rows])

    note = ""
    if truncated or len(rows) > max_rows:
        note = f"\n(Showing first {min(len(rows), max_rows)} rows only.)"

    user_msg = (
        f"Question: {question}\n\n"
        f"SQL:\n{sql}\n\n"
        f"Columns: {columns}\n"
        f"Rows ({len(rows)}):\n{preview}{note}"
    )

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )

    return response.choices[0].message.content.strip(), response.usage
