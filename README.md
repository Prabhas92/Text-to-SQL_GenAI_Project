# Text-to-SQL Assistant

A production-style Natural Language to SQL assistant built with Python, OpenAI, and SQLite.

## Project Overview

This project converts natural-language business questions into SQL queries, validates the generated SQL through deterministic guardrails, executes approved queries against a read-only database, and returns the results in natural language.

## Architecture

```text
User Question
      ↓
Schema + Context
      ↓
LLM SQL Generation
      ↓
SQL Guardrails
      ↓
Read-Only Database
      ↓
Results
      ↓
Natural Language Answer
```

# Tech Stack
- Python
- OpenAI API
- Pydantic
- SQLite
- SQL
- Git 

# GitHub Project Status:
🚧 Under development