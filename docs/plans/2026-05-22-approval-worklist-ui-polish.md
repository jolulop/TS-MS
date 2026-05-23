# Approval Worklist UI Polish

## Goal

Polish the approval workspace so the `TS_ADMIN` oversight view and approval
detail screen use the same `Approval Worklist` naming and a denser,
report-style layout.

## Scope

- rename the admin-facing page title from `Approval Oversight` to
  `Approval Worklist`
- shorten employee and approver labels to employee name only when an actual
  employee is present
- add `TS Submission Date` to the pending approval grid
- compact the approval detail context into a single top section and move the
  related links section below it

## Implementation Notes

- keep the underlying admin-oversight behavior, filters, and permissions
  unchanged
- preserve role-label fallback for GCC approval items with role-based approvers
- keep the detail page read-only for oversight-only viewers

## Validation

- update focused approval worklist/detail UI tests
- update any project-management drill-down expectations that still assert the
  old `Approval Oversight` page title
