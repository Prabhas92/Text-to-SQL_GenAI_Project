# Text-to-SQL Assistant

A production-style Natural Language to SQL assistant built with Python, OpenAI, and SQLite. 

## Project Overview

This project converts natural-language business questions into SQL queries, validates the generated SQL through deterministic guardrails, executes approved queries against a read-only database, and returns the results in natural language.

## Architecture

```text
User Question (+ last 3 turns of conversation)
      ↓
Schema + Context            schema.py      DDL, sample rows, allowed values
      ↓
LLM SQL Generation          generator.py   gpt-4o-mini, strict JSON output
      ↓                                    (is_answerable, sql, tables_used, explanation)
SQL Guardrails              guardrails.py  SELECT-only, single statement, keyword
      ↓                                    block-list, EXPLAIN compile, table allow-list
Read-Only Database          executor.py    mode=ro, authorizer, 5s timeout, 200-row cap
      ↓
  error? ──► send error back to the LLM and retry (max 3 attempts)
      ↓
Natural Language Answer     answerer.py
```

`pipeline.py` wires these together; `app.py` is the Streamlit UI.

## Project Layout

| File | Purpose |
|---|---|
| `DB_Scripts/create_db.py` | Builds `retail.db` (100 customers, 20 products, 1,500 orders) |
| `schema.py` | Turns the database into an LLM-friendly schema description |
| `generator.py` | Question → structured SQL via OpenAI |
| `guardrails.py` | Deterministic SQL safety checks |
| `executor.py` | Runs approved SQL with read-only, timeout and row limits |
| `answerer.py` | Rows → short plain-English answer |
| `pipeline.py` | End-to-end flow with self-correction; also an interactive CLI |
| `app.py` | Streamlit chat UI |
| `tests/` | Guardrail and executor unit tests (no API key needed) |
| `evals/` | Gold question set + execution-accuracy evaluator |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then put your OPENAI_API_KEY in .env
python DB_Scripts/create_db.py  # optional: retail.db is already committed
                                # (run from inside DB_Scripts/ to overwrite it)
```

## Run

```bash
streamlit run app.py            # web UI
python pipeline.py              # terminal chat
pytest -q                       # guardrail tests (offline)
python evals/run_eval.py        # accuracy on the gold set
```

## Safety Model

The LLM is treated as untrusted. Generated SQL must pass every layer:

1. **Prompt rules**: read-only, schema-only, business definitions.
2. **Static checks**: one statement, starts with `SELECT`/`WITH`, no `INSERT/UPDATE/DELETE/DROP/PRAGMA/ATTACH/...`.
3. **Compile check**: `EXPLAIN` catches syntax errors and unknown columns without running the query.
4. **Table allow-list**: every table the compiled program opens must be allowed (this catches `JOIN ... USING`, which SQLite's authorizer misses).
5. **Runtime**: read-only connection + authorizer + timeout + row cap.

## Results

`python evals/run_eval.py` → **17/18 (94%)** execution accuracy on the gold set, including 3/3 correctly refused unanswerable questions. The one miss ("average number of items per order") is a real ambiguity: line items vs. units.

## Tech Stack
- Python
- OpenAI API (gpt-4o-mini, structured outputs)
- Pydantic
- SQLite
- Streamlit
- pytest
