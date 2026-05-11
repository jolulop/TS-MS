# Stack Choice

## Goal

Describe the current repository stack that supports fast local iteration and the implemented server-rendered Timesheet Management System.

## Selected stack

- Python 3.12
- Django monolith
- Server-rendered HTML templates
- JSON API endpoints under `/api/v1` for implemented session, admin, timesheet, and approval flows
- Ruff for formatting and linting
- pytest with `pytest-django`
- GitHub Actions for CI
- Environment-driven database configuration

## Database strategy

The repository supports two database modes:

- SQLite bootstrap mode for zero-friction local startup
- PostgreSQL mode for CI and later Azure deployment parity

This keeps local setup simple while preserving a direct path to PostgreSQL-backed environments.

## Why this stack

- Django gives us one deployable and one mental model across System Management, TS Management, approvals, and reporting.
- Server-rendered templates keep the UI consistent with the implemented codebase and reduce unnecessary frontend split complexity.
- Ruff and pytest provide a fast, low-maintenance quality toolchain.
- Environment-driven settings are compatible with local development, CI, and Azure hosting.

## Not chosen

- Separate frontend and backend applications
- Client-heavy SPA architecture
- Container orchestration
- Full Azure deployment automation

Those can be revisited later if the product outgrows the current monolith.
