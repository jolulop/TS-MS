# Project Missing Timesheets Report

## Goal

Add a project-scoped missing-timesheets report that is available to
`PROJECT_OWNER`, `PROJECT_MANAGER`, and `TS_ADMIN`, with CSV export support in
both the UI and API.

## Scope

In scope:

- broaden the existing `missing-timesheets` report audience
- use project multi-select filters based on caller scope
- report missing employee weekly timesheets by project assignment window
- add HTML CSV export
- add API endpoints that return a CSV export URI and a downloadable CSV file
- write audit events for report generation and CSV export
- update tests and v5.5 documentation

Out of scope:

- persistent exported-file storage
- background report generation
- changing unrelated report layouts or export flows

## Approach

- upgrade the current `missing-timesheets` report instead of adding a second
  similarly named report
- derive report scope from accessible projects:
  - `PROJECT_OWNER`: owned projects
  - `PROJECT_MANAGER`: managed projects
  - both roles: union of owned and managed projects
  - `TS_ADMIN`: projects visible through current Office and Business Unit scope
- compute missing weeks only for employees assigned to the selected projects,
  deduplicated by employee and week
- use direct CSV download responses for browser export and a lightweight API
  export-URI creation flow

## Verification

- targeted UI and API tests for report visibility, filtering, CSV export, and
  audit events
- `python manage.py check`
