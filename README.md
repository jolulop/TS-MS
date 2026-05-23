# Timesheet Management System

This repository contains the Timesheet Management System (TS Management) project.

## Current implemented scope

The repository now contains an implemented Django application, not only a foundation scaffold. Current features include:
- internal session initialization after external email validation
- Office and Business Unit administration
- Office-level configuration inherited by Business Units at runtime
- employee management, roles, and Business Unit scope
- Office-level Clients, Cost Centers, and Pricing Models
- Business Unit-level Internal Categories and General Charge Codes
- Office-level Yearly Calendars with Special Days
- Business Unit-specific Calendar Period Rules inside shared Office calendars
- dedicated Cross-Office Staffing for employees working on other Offices' projects
- weekly timesheets, approvals, and project time inquiry
- target-project approval visibility and admin oversight for cross-office project time
- user-initiated `Copy Prev. Week` timesheet creation when enabled by Office configuration
- guarded delete actions for selected System Management entities

## Stack

- Python 3.12
- Django monolith
- server-rendered HTML templates
- SQLite bootstrap fallback for local setup
- PostgreSQL support for parity environments
- Ruff for linting and formatting
- pytest with `pytest-django`

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

## Common commands

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

## Documentation baseline

Current repository-aligned specification set:
- `docs/specification-index-v6.1.md`
- `docs/functional-spec-v6.1.md`
- `docs/ui-screen-spec-v6.1.md`
- `docs/integration-api-spec-v6.1.md`
- `docs/authorization-matrix-v6.1.md`
- `docs/business-rules-catalog-v6.1.md`
- `docs/use-cases-acceptance-v6.1.md`
- `docs/data-model-erd-v6.1.md`
- `docs/non-functional-requirements-v6.1.md`

Legacy `v5.2`, `v5.4`, `v5.5`, `v5.6`, `v5.7`, `v5.8`, `v5.9`, `v5.9.1`, `v5.9.2`, `v5.9.3`, `v5.9.5`, and `v6.0` markdown notes remain in `docs/` only as historical superseded deltas and should not be used as the current source of truth.

## Repository guidance

Before implementing business features, follow:
- `AGENTS.md`
- `PLANS.md`
- `docs/specification-index-v6.1.md`
- `docs/architecture/stack.md`
- `docs/development/local-setup.md`
- `docs/development/reference-data-strategy.md`
