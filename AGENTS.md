# AGENTS.md

## Purpose

This repository contains the **Timesheet (TS) Management System**.

Treat this file as the repository-level implementation guide for the current Django codebase.

## Current source of truth

Use these documents first when implementing or updating behavior:

1. `docs/specification-index-v8.0.md`
2. `docs/functional-spec-v8.0.md`
3. `docs/use-cases-acceptance-v8.0.md`
4. `docs/data-model-erd-v8.0.md`
5. `docs/authorization-matrix-v8.0.md`
6. `docs/ui-screen-spec-v8.0.md`
7. `docs/integration-api-spec-v8.0.md`
8. `docs/business-rules-catalog-v8.0.md`
9. `docs/non-functional-requirements-v8.0.md`

Legacy `v5.2`, `v5.4`, `v5.5`, `v5.6`, `v5.7`, `v5.8`, `v5.9`, `v5.9.1`, `v5.9.2`, `v5.9.3`, `v5.9.5`, `v6.0`, `v6.1`, `v7.0`, and `v7.1` markdown notes in `docs/` are historical only and are not the current implementation source of truth.

If code and docs conflict, do not silently guess. Prefer the newest approved spec doc, then align code to it.

## Product summary

The product is a web-based enterprise Timesheet Management System with these functional blocks:
- `System Management`
- `TS Management`
- `Approvals`
- `Reports`

Core business themes:
- weekly Monday-starting timesheets
- optional configured weekend chargeability by Business Unit calendar period rule
- employee, project, and general charge-code time charging
- cross-office project staffing with employee home-office calendar and GCC behavior
- internal role-based authorization after external email validation
- Office context plus Business Unit scoped administration
- approval workflows
- auditability
- retention and archive

## Mandatory business rules

### Authentication and authorization

- External access validation is used only once at access time to validate the user email.
- After access validation, the TS system identifies the user internally using `employee.email`.
- All post-login authorization is handled internally.
- Roles come from TS data, not from the external validation system.
- Supported internal roles:
  - `USER`
  - `TS_ADMIN`
  - `TS_ADMIN_MASTER`
  - `PROJECT_OWNER`
  - `PROJECT_MANAGER`
- Deny by default.
- Row-level scope must be enforced server-side.

### Timesheet rules

- One employee can have at most one weekly timesheet per week.
- A timesheet week starts on Monday.
- Weekend entry is blocked by default.
- Weekend entry is allowed only when the effective Business Unit calendar period rule enables Saturday and/or Sunday and no active Special Day overrides that date.
- Employees can charge only to:
  - active assigned projects for the work date, including valid cross-office staffing, or
  - valid general charge codes for the work date.
- Daily hour limits come from the effective calendar period rule.
- Approved timesheets are locked.
- Archived timesheets are not editable.

### Project rules

- Projects belong to one Business Unit.
- Project Owner must have the `PROJECT_OWNER` role.
- Project Manager must have the `PROJECT_MANAGER` role.
- `client`, `internal category`, `cost center`, and `pricing model` are mandatory on every project.
- `client`, `cost center`, and `pricing model` are Office-scoped masters.
- Closed projects cannot receive new time after close date.

### Administrative scope

- TS Admins act only within assigned Business Units.
- Active Office context must also be enforced server-side.
- Project Owners act within owned-project scope.
- Project Managers act within managed-project scope.

### Audit

Always preserve auditability for:
- employee identity changes
- role changes
- BU scope changes
- project ownership and management changes
- timesheet submit, withdraw, reopen, archive, restore
- approval approve and reject
- guarded administrative deletes
- imports and exports

## Current implementation stack

Follow the existing stack instead of introducing a new architecture:

- Python 3.12
- Django monolith
- server-rendered HTML templates
- JSON API endpoints under `/api/v1` where implemented
- SQLite bootstrap for local setup
- PostgreSQL-compatible configuration for parity environments
- Ruff
- pytest
- pytest-django

Current repository layout:

```text
/apps
  /audit
  /auth
  /common
  /core
  /integrations
  /master_data
  /reference_data
  /timesheets

/config
/docs
/tests
```

## Working conventions

### Read before changing code

Read only the docs and code relevant to the task. Do not scan the entire repo unless needed.

### Plan first for multi-step work

Create or update a plan in `docs/plans/` when the task is:
- ambiguous
- cross-module
- larger than one small PR
- schema-changing
- auth or security sensitive
- workflow-changing

Use a file named:

```text
docs/plans/<yyyy-mm-dd>-<short-task-name>.md
```

### Small, reviewable changes

Prefer incremental changes over large rewrites.

### Thin views, rich services

- Keep Django views thin.
- Keep business rules in services, validators, and policy helpers.
- Do not duplicate authorization logic casually.
- Never trust UI-only validation.

## Architecture rules

Preferred domain boundaries in the current codebase:
- `auth`
- `offices`
- `employees`
- `business-units`
- `reference-data`
- `calendars`
- `clients`
- `pricing-models`
- `internal-categories`
- `cost-centers`
- `general-charge-codes`
- `projects`
- `project-assignments`
- `timesheets`
- `approvals`
- `reports`
- `integrations`
- `audit`

Use transactional boundaries for critical state transitions:
- submit timesheet
- approve or reject approval item
- reopen timesheet
- archive or restore
- guarded delete flows when audit and dependent cleanup must stay consistent

## Authorization implementation rules

All post-login authorization is internal.

Use internal sources only:
- employee status
- employee roles
- employee Office
- employee BU scope
- project owner relationship
- project manager relationship
- timesheet ownership
- entity state

Apply row-level filtering in DB queries rather than filtering sensitive data in memory.

## Data model rules

Preserve these constraints:
- unique employee email strategy
- one primary BU per employee
- one weekly timesheet per employee/week
- exactly one charging target on a timesheet line: project xor general charge code
- no overlapping calendar period rules in the same Business Unit and Yearly Calendar
- mandatory project classification fields
- immutable or append-only approval action history

Prefer status-based lifecycle over hard delete.
Do not physically delete transactional records unless an approved spec explicitly requires it.

Use forward-only migrations. Do not edit old applied migrations.

## API rules

- REST + JSON where JSON endpoints exist
- versioned base path: `/api/v1`
- structured error responses
- stable business error codes
- not every server-rendered UI action has a matching JSON endpoint

Keep controllers thin and never expose unauthorized rows.

## UI rules

Implement the two-block navigation exactly:
- `System Management`
- `TS Management`

Supporting top-level areas currently implemented:
- `Approvals`
- `Reports`
- `Profile`

Hide unauthorized menus and actions, but keep backend authorization authoritative.
Use read-only states where users may view but not edit.

## Testing rules

Add or update tests whenever behavior changes.

Required coverage focus:
- validators and policy services
- admin CRUD and guarded delete flows
- project and assignment rules
- calendar rule resolution
- timesheet create, save, submit, reopen, archive, restore
- approval workflow
- reporting scope enforcement

## Definition of done

A task is done only when:
1. behavior matches the applicable specs
2. code compiles or checks cleanly
3. relevant tests pass
4. changed business rules are covered by tests
5. authorization is enforced server-side
6. audit events are added for sensitive operations
7. migrations and seed/reference data are included when needed
8. docs are updated when behavior changes
9. UI states match role and status rules
10. the task summary explains what changed, how it was verified, and any open issues

## Commands

Prefer the repository Makefile:

```bash
make install
make run
make migrate
make seed
make seed-dev
make lint
make format
make format-check
make test
make check
```

## Final note

Keep this file practical. If repeated mistakes appear during development, update this file with a concrete rule that matches the implemented codebase.
