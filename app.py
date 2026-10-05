import pandas as pd
import streamlit as st

from guardrails import validate_sql
from pipeline import TextToSQL

# ============================================================
# app.py — Streamlit demo UI
#
#   streamlit run app.py
# ============================================================

st.set_page_config(page_title="Text-to-SQL Assistant", page_icon="🗄️", layout="wide")


@st.cache_resource
def get_bot():
    return TextToSQL()


bot = get_bot()

EXAMPLES = [
    "Which city has the most customers?",
    "Top 5 products by revenue",
    "Monthly revenue for the last 6 months",
    "What share of orders were cancelled or returned?",
    "Who are our top 10 customers by total spend?",
    "What is our profit margin per product?",
]

if "messages" not in st.session_state:
    st.session_state.messages = []   # rendered chat
    st.session_state.history = []    # question -> sql memory for the LLM


# ------------------------------------------------------------
# Sidebar: schema, examples, guardrail playground
# ------------------------------------------------------------
with st.sidebar:
    st.header("🗄️ Database")
    st.caption(f"`{bot.db_path.split('/')[-1]}` · tables: {', '.join(bot.tables)}")
    with st.expander("Schema the LLM sees"):
        st.code(bot.schema_text, language="sql")

    st.header("💡 Try asking")
    for ex in EXAMPLES:
        if st.button(ex, width="stretch"):
            st.session_state.pending = ex

    st.header("🛡️ Guardrail playground")
    st.caption("Paste any SQL to see if it would be allowed to run.")
    raw = st.text_area("SQL", "DELETE FROM orders WHERE 1=1;", height=90)
    if st.button("Check SQL"):
        g = validate_sql(raw, bot.db_path, bot.tables)
        if g.ok:
            st.success(f"Allowed · reads {g.tables_read}")
        else:
            st.error(f"Blocked · {g.reason}")

    if st.button("🧹 Clear conversation"):
        st.session_state.messages = []
        st.session_state.history = []
        st.rerun()


# ------------------------------------------------------------
# Rendering one assistant answer
# ------------------------------------------------------------
def render_answer(a):
    if a.status == "unanswerable":
        st.warning(f"**Can't answer from this database.** {a.answer}")
    elif a.status == "failed":
        st.error(a.answer)
    else:
        st.markdown(a.answer)

    if a.rows:
        df = pd.DataFrame(a.rows, columns=a.columns)

        tab_table, tab_chart = st.tabs(["Table", "Chart"])
        with tab_table:
            st.dataframe(df, width="stretch", hide_index=True)
            if a.truncated:
                st.caption(f"Showing first {len(df)} rows.")
        with tab_chart:
            numeric = df.select_dtypes("number").columns.tolist()
            labels = [c for c in df.columns if c not in numeric]
            if labels and numeric and len(df) > 1:
                st.bar_chart(df, x=labels[0], y=numeric[0])
            else:
                st.caption("No obvious chart for this result.")

    with st.expander("🔍 How I got this"):
        for i, att in enumerate(a.attempts, 1):
            if att.error:
                st.markdown(f"**Attempt {i} — rejected at {att.stage}:** `{att.error}`")
                st.code(att.sql, language="sql")
        if a.sql:
            st.markdown(f"**Final SQL** · reads `{', '.join(a.tables_read)}`")
            st.code(a.sql, language="sql")
        if a.explanation:
            st.caption(a.explanation)
        st.caption(
            f"Status: {a.status} · attempts: {len(a.attempts)} · "
            f"tokens: {a.total_tokens} · latency: {a.latency_s:.1f}s"
        )


# ------------------------------------------------------------
# Main chat
# ------------------------------------------------------------
st.title("Text-to-SQL Assistant")
st.caption("Ask a business question in plain English → guarded SQL → answer.")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            render_answer(m["content"])

question = st.chat_input("e.g. Revenue by city this year")
question = question or st.session_state.pop("pending", None)

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Generating SQL…"):
            answer = bot.ask(question, st.session_state.history)
        render_answer(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    if answer.status == "ok":
        st.session_state.history.append({"question": question, "sql": answer.sql})
