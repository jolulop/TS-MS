# 2026-05-17 Project Management UI

## Goal

Add a new `TS/Project Management > Project Management` screen for
`TS_ADMIN`, `PROJECT_OWNER`, and `PROJECT_MANAGER` that consolidates
project browsing and links into the existing project, approval, and
reporting UIs.

## Scope

- add a new left-navigation entry under `TS/Project Management`
- add a new role-aware project-management page under the TS area
- support status filters: `All`, `Active`, `Closed`, `Draft`
- show summary columns:
  - project name
  - status
  - approved hours
  - pending timesheets
  - missing timesheets
- add role-aware drill-down links from the summary grid
- make the pending-timesheet drill-down usable for project owners
- allow project owners to open the project detail screen in read-only mode

## Design Notes

- Implement this as one shared layout and data pass instead of per-role
  variations so the same screen can serve `TS_ADMIN`, `PROJECT_OWNER`,
  and `PROJECT_MANAGER`.
- Keep the new page in the TS area because it is an operational
  management view, not a replacement for the System Management project
  master-data collection.
- Reuse existing scoped-project rules already used by the project-time
  and missing-timesheets reports.
- Keep `TS_ADMIN` as the only role with live project write actions in the
  System Management project detail screen unless the new requirement
  explicitly says otherwise.
- Let `PROJECT_OWNER` open the existing project detail screen in a
  read-only form layout for owned projects so the new summary-grid name
  link works without silently granting full admin write authority.

## Pending Decisions Resolved

- `Project Name` drill-down:
  - `TS_ADMIN`: editable project detail
  - `PROJECT_OWNER`: read-only project detail for owned projects
  - `PROJECT_MANAGER`: no link
- `Pending TS` drill-down:
  - opens `Approval Worklist`
  - extend worklist visibility so `PROJECT_OWNER` can view pending and
    decided approval items for owned projects, but not approve or reject
    unless another approval rule already grants that authority
- Missing-timesheet counting:
  - count missing weeks within the effective assignment window up to the
    current Monday
  - a week counts as missing unless a timesheet exists in `SUBMITTED` or
    `APPROVED` status for that employee and week

## Out of Scope

- new APIs
- approval workflow routing changes
- new audit event types
- changes to project create/edit business rules beyond access needed for
  the new navigation path
