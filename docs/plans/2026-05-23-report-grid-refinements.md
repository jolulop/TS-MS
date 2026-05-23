# Report Grid Refinements

## Goal

Refine the current report viewer outputs for:

- `Reports > Project Time Report`
- `Reports > Pending Approvals`

## Scope

- add a weekly summary grid above the Project Time detailed results grid
- adjust Pending Approvals columns to show week-start context first and remove
  the internal approval-item identifier and status column

## Implementation Notes

- keep the existing detailed Project Time line grid and CSV export
- add the weekly summary as an additional report-viewer table above the main
  results grid
- keep the Pending Approvals filters, scope rules, and CSV export flow intact
  while reshaping the visible/report-exported columns

## Validation

- update report UI tests for the extra Project Time summary grid
- update Pending Approvals report/grid and CSV expectations
