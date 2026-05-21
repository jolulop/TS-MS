# Project Management Pending Approval Drill-Down

## 1. Goal

Make the `Pend. Appr.` project-summary cell in `TS/Project Management >
Project Management` open the Approval Worklist for the matching project when
the visible pending count is greater than zero.

## 2. Scope

In scope:
- update the `Pend. Appr.` project-summary cell behavior
- reuse the existing `/approvals/?project_id=<id>` filtered worklist route
- allow the drill-down for users who can already access the row and the
  Approval Worklist
- keep zero counts as plain text
- update focused UI docs and tests

Out of scope:
- new Approval Worklist routes
- approval authorization changes
- changes to pending-count calculation

## 3. Design

- keep the current Project Management summary grid
- render the `Pend. Appr.` cell as a link only when:
  - the pending count is greater than zero
  - the current role can open the Approval Worklist
- preserve the existing `project_id` filter behavior in the Approval Worklist

## 4. Validation

- `PROJECT_OWNER`, `PROJECT_MANAGER`, and `TS_ADMIN` can drill into a nonzero
  project pending count within their visible project scope
- zero counts do not render as links
- the worklist opens filtered to the selected project
