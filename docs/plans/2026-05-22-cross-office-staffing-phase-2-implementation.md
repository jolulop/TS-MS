# Cross-Office Staffing Phase 2 Implementation

## Scope

Implement the approved `v6.0` Phase 2 behavior so cross-office staffing is
treated as valid project staffing for:

- timesheet project charging eligibility
- weekly timesheet available-project lists
- TS/Project Management staffing-derived missing-timesheet summaries
- `Missing Timesheets by Project` staffing windows
- project-facing report and approval validation coverage

## Approved Behavior Anchor

Phase 2 follows the approved `v6.0` source-of-truth updates:

- `docs/functional-spec-v6.0.md`
- `docs/use-cases-acceptance-v6.0.md`
- `docs/ui-screen-spec-v6.0.md`
- `docs/business-rules-catalog-v6.0.md`

Key rules:

- employees may charge a project when the work date is covered by either:
  - active normal `ProjectAssignment`
  - active `CrossOfficeProjectAssignment`
- home-office calendar, calendar period rules, and GCC context remain unchanged
- target-project approval and project-time reporting must include valid
  cross-office staffed employees
- project missing-timesheet logic must use both staffing models

## Implementation Slices

### 1. Shared staffing helper

Add a shared staffing helper module that normalizes:

- active staffing existence for one employee/project/work date
- active project availability for one employee across a week window
- active staffing windows across selected projects for summary/report use

This avoids duplicating cross-office union logic in:

- `apps/timesheets/services.py`
- `apps/core/ts_views.py`
- `apps/core/reports_views.py`

### 2. Timesheet eligibility

Update timesheet behavior so:

- timesheet editor available-project lists include cross-office staffed projects
- project line validation accepts active cross-office staffing on the work date

No Phase 2 changes are required to:

- calendar special-day blocking
- weekend/day-limit logic
- GCC availability logic

Those already follow the employee home-office context.

### 3. Project Management summaries

Update staffing-derived summary logic so:

- missing-timesheet project counters use both staffing models

Approved-hours and pending-approval counts already derive from charged project
lines and therefore should work automatically once valid cross-office time can
be entered.

### 4. Report and approval union behavior

Update report staffing windows so:

- `Missing Timesheets by Project` includes cross-office staffed employees

Validate that existing project-based flows continue to work for cross-office
time once the timesheet line exists:

- `Project Time Report`
- `Pending Approvals` report for project approvers
- approval worklist visibility for target-project approvers

## Planned Tests

- `tests/test_timesheet_engine.py`
  - cross-office staffed project appears in available projects
  - cross-office staffed project line saves and submits successfully
- `tests/test_project_management_ui.py`
  - missing-timesheet summary counts include cross-office staffing
- `tests/test_reports_ui.py`
  - project-time and pending-approvals flows include cross-office staffed
    employees
  - missing-timesheets report includes cross-office staffed missing employees

## Deferred Beyond Phase 2

- target-project-office `TS_ADMIN` approval oversight expansion
- analytics attribution changes that re-label BU/Office away from the
  weekly-timesheet home BU
- employee detail read-only cross-office staffing section
