# Report Viewer Layout Standardization

## 1. Goal

Standardize the remaining operational reports in `System Management > Reports`
to the same stacked report-viewer layout already used by the newer admin
analytics reports.

## 2. Scope

In scope:
- update these reports to use a top stacked filter section and a second stacked
  totals section:
  - Project Time Report
  - Pending Approvals
  - Missing Timesheets by Project
  - Archived Timesheets
  - Audit History
  - Integration Jobs
- preserve each report's existing filters, totals, result rows, authorization,
  and CSV behavior
- update tests and current `v5.9.5` UI docs

Out of scope:
- report data logic changes
- new filters or totals
- export behavior changes

## 3. Design

- keep the shared `core/report_viewer.html` template
- move the targeted reports onto the same stacked top layout class used by
  `Employee Utilization` and `Office / BU Time Summary`
- retain dense filter grids where they are already helpful, such as
  `Audit History`

## 4. Validation

- targeted reports render the stacked filter/totals layout
- result grids and exports remain available
- existing scope and role behavior stay unchanged
