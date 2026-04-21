# Local Setup

## Prerequisites

- WSL-enabled development environment
- Python 3.12
- GNU Make

Optional for parity work:
- PostgreSQL 16+

## Bootstrap

1. Create a virtual environment:
   `python3 -m venv .venv`
2. Activate it:
   `source .venv/bin/activate`
3. Install dependencies:
   `python -m pip install -e .[dev]`
4. Copy the environment template:
   `cp .env.example .env`
5. Apply migrations:
   `python manage.py migrate`
6. Seed mandatory reference data:
   `python manage.py seed_reference_data`
7. Start the app:
   `python manage.py runserver`

## Database modes

### Default bootstrap mode

The scaffold defaults to SQLite through:

`TSMS_DB_BACKEND=sqlite`

This is the fastest path to a working local setup during the foundation phase.

### PostgreSQL mode

Set these environment variables to use PostgreSQL:

- `TSMS_DB_BACKEND=postgres`
- `TSMS_DB_NAME`
- `TSMS_DB_USER`
- `TSMS_DB_PASSWORD`
- `TSMS_DB_HOST`
- `TSMS_DB_PORT`

## Validation commands

- `make lint`
- `make format-check`
- `make test`
- `make check`

Run these before preparing a commit.
