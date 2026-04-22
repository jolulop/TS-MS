# Timesheet Management System

This repository contains the Timesheet Management System (TS Management) project.

## Current scope

The repository is currently in a Phase 1 foundation stage:
- Python 3.12 target
- Django monolith for local-first development
- env-driven database configuration with a zero-friction SQLite bootstrap path
- PostgreSQL support for later Azure parity and CI use
- Windows + WSL + VS Code development workflow
- Azure App Service as the later deployment target

## Local development approach

Use WSL for Python commands and virtual environment management.

Planned stack:
- Django
- server-rendered HTML templates
- responsive UI shell
- SQLite bootstrap fallback for local setup
- PostgreSQL for CI and later Azure parity
- Ruff for formatting and linting
- pytest for automated tests
- GitHub Actions for CI

## Initial setup

1. Open the repository in VS Code using the WSL extension.
2. Create a virtual environment in WSL:
   `python3 -m venv .venv`
3. Activate it:
   `source .venv/bin/activate`
4. Install the project and dev dependencies:
   `python -m pip install -e .[dev]`
5. Copy `.env.example` to `.env` and adjust values if needed.
6. Apply the baseline migrations:
   `python manage.py migrate`
7. Seed the mandatory reference data:
   `python manage.py seed_reference_data`
8. Optional: load local sample data for browsing the UI:
   `python manage.py seed_dev_data`

## Daily commands

- Start the app: `make run`
- Run migrations: `make migrate`
- Seed reference data: `make seed`
- Seed local dev sample data: `make seed-dev`
- Lint the repo: `make lint`
- Check formatting: `make format-check`
- Format files: `make format`
- Run tests: `make test`
- Run Django checks: `make check`

## Local UI sample login

After running `make seed-dev`, you can initialize a TS Admin session in the access-entry screen with:

- `jose.luis.lopez@timia.ai`

## Repository guidance

Before implementing business features, follow:
- `AGENTS.md`
- `PLANS.md`
- `docs/plans/2026-04-20-phase-1-core-timesheet-flow.md`
- `docs/architecture/stack.md`
- `docs/development/local-setup.md`
- `docs/development/reference-data-strategy.md`
