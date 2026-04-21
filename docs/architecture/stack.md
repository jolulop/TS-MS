# Stack Choice

## Goal

Choose a simple stack that supports fast local iteration now and a clean Azure path later, without splitting the system into multiple deployables too early.

## Selected stack

- Python 3.12
- Django monolith
- Server-rendered HTML templates
- Ruff for formatting and linting
- pytest with `pytest-django`
- GitHub Actions for CI
- Environment-driven database configuration

## Database strategy

The current scaffold supports two database modes:

- SQLite bootstrap mode for zero-friction local startup during the foundation phase
- PostgreSQL mode for CI and later Azure deployment parity

This keeps Phase 1 easy to run while preserving a direct upgrade path to PostgreSQL-backed environments.

## Why this stack

- Django gives us one deployable and one mental model while the domain is still forming.
- Server-rendered templates keep frontend scope intentionally small in Phase 1.
- Ruff and pytest provide a fast, low-maintenance quality toolchain.
- Environment-driven settings are compatible with local development, CI, and Azure hosting.

## Not chosen in Phase 1

- Separate frontend and backend applications
- Client-heavy SPA architecture
- Container orchestration
- Full Azure deployment automation

Those can be revisited once the core business workflows are stable.
