# Cross-Office Staffing Phase 3 Implementation

## Scope

Implement the approved Phase 3 admin oversight behavior for cross-office
project approval items.

## Goal

Make `TS_ADMIN` approval oversight follow the target project Office/Business
Unit for project approval items while keeping General Charge Code approval
oversight on the weekly-timesheet home Business Unit side.

## Rules

- Project approval items:
  - visible to `TS_ADMIN` when the target project belongs to the admin's
    active Office and scoped Business Units
  - no longer visible just because the employee's weekly-timesheet home
    Business Unit is in scope
- General Charge Code approval items:
  - continue to follow weekly-timesheet home Business Unit scope
- `TS_ADMIN` oversight remains read-only for approval decisions
- existing Office / BU summary attribution outside approval-specific screens
  remains on the weekly-timesheet home Business Unit side

## Code Areas

- `apps/timesheets/approval_scope.py`
  - shared visibility and effective-BU helpers
- `apps/auth/policies.py`
  - approval item detail authorization
- `apps/timesheets/services.py`
  - approval item list/detail serialization
- `apps/core/reports_views.py`
  - pending approvals report
  - approval turnaround report
  - report hub counts

## Tests

- target-office `TS_ADMIN` can see cross-office project approval items in the
  approval worklist and detail view
- home-office `TS_ADMIN` does not see those project approval items from the
  approval oversight side
- target-office `TS_ADMIN` pending-approvals and approval-turnaround reports
  include the cross-office item
- approval-specific `BU` labels show target project BU for project approval
  items and home BU for GCC items
