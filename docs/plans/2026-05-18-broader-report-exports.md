# Broader Report CSV Exports

## 1. Goal

Extend the current report viewer so the existing operational reports can export
their filtered scoped rows to CSV, reusing the existing Missing Timesheets by
Project export pattern where it fits.

## 2. Scope

In scope:
- HTML CSV export for:
  - Project Time
  - Pending Approvals
  - Missing Timesheets by Project
  - Archived Timesheets
  - Audit History
  - Integration Jobs
- shared export route and CSV response logic
- export audit events
- tests and current v5.6 docs

Out of scope:
- new report definitions
- BI-style aggregation work
- widening `/api/v1` export endpoints beyond the current Missing Timesheets by
  Project API flow

## 3. Source Documents

- `docs/specification-index-v5.6.md`
- `docs/functional-spec-v5.6.md`
- `docs/ui-screen-spec-v5.6.md`
- `docs/use-cases-acceptance-v5.6.md`
- `docs/integration-api-spec-v5.6.md`
- `docs/business-rules-catalog-v5.6.md`

## 4. Design

- keep the shared report viewer template
- use the existing report builder `headers` + `rows` payload as the CSV source
- add one generic HTML export route for exportable reports
- preserve the dedicated Missing Timesheets by Project API export behavior
- audit every CSV export with report code, active filters, and row count

## 5. Risks

- export routes must not widen report scope beyond the visible report grid
- audit export should not regress the existing Missing Timesheets API behavior
- broad CSV export should stay consistent with the filter state shown in the UI
