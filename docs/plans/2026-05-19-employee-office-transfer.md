# Employee Office Transfer

## Status

- completed
- date: `2026-05-19`

## Goal

Add a supported cross-Office employee transfer workflow that preserves source
history by archiving the old employee record and creating a new active employee
record in the target Office.

## Source Documents

- user-approved transfer procedure in the active task thread
- `docs/functional-spec-v5.9.md`
- `docs/ui-screen-spec-v5.9.md`
- `docs/authorization-matrix-v5.9.md`
- `docs/business-rules-catalog-v5.9.md`
- `AGENTS.md`

## Scope

- add a master-only System Management entry point for Employee Transfers
- add a dedicated transfer screen instead of overloading normal employee edit
- implement transactional transfer service logic
- archive the old employee email and deactivate the old employee record
- create the new employee in the target Office with target Business Unit scope
  and roles
- preserve source-office historical records on the old employee
- block unsafe transfers when active operational dependencies still point to
  the source employee
- add tests and update the v5.9 docs

## Key Decisions

- authorization: `TS_ADMIN_MASTER` only
- transfer model: safe archive-and-recreate, not in-place Office mutation
- source `employee_id` remains historical; target Office gets a new
  `employee_id`
- old employee email is rewritten to an archival email so the real login email
  can move to the new employee record
- old employee code stays unchanged; the transfer form requires a new unique
  employee code for the created target-office employee

## Validation And Guardrails

- source employee must exist and be active
- source and target Offices must be different
- target Office must be active
- target primary Business Unit and target Business Unit scope must belong to the
  target Office
- target primary Business Unit must be included in target scope
- source employee cannot be the current logged-in actor
- transfer is blocked when the source employee still has active operational
  dependencies that would leave live source-office workflows pointing to an
  inactive person

## UI Shape

- new System Management navigation entry: `Employee Transfers`
- new standalone screen:
  - first select the source employee
  - then review source summary and transfer-readiness information
  - then enter target setup:
    - new employee code
    - target Office
    - target primary Business Unit
    - target additional Business Units
    - target roles
    - archived email preview
- success state shows the archived source employee and the newly created target
  employee summary

## Audit Expectations

- audit old employee status change
- audit old employee email archive change
- audit old employee role/BU scope deactivation
- audit new employee creation
- audit new employee role/BU assignments
- audit a dedicated transfer summary event linking old and new records

## Verification Plan

- focused UI tests for master-only access, source selection, success flow, and
  blocked validation paths
- focused service/API-adjacent tests through the UI flow for email archive,
  new employee creation, and dependency blocking
- `manage.py check`
- targeted `ruff` on touched files

## Verification Completed

- `ruff` clean on touched Python files
- `manage.py check` clean
- `tests/test_system_management_ui.py` passed
- `tests/test_ui_shell.py` passed
