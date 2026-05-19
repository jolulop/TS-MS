# Advanced Report Expansion

## 1. Goal

Expand the live reporting surface with a first advanced analytics tier for
`TS_ADMIN` using the existing shared report viewer and CSV export pattern.

## 2. Scope

In scope:
- add `Employee Utilization`
- add `Office / BU Time Summary`
- add `General Charge Code Usage`
- add `Approval Turnaround`
- add server-side filters, scoped result grids, totals, and CSV export for
  those reports
- enforce `TS_ADMIN` authorization and scoped Business Unit access
- update tests and current `v5.8` docs

Out of scope:
- new JSON `/api/v1` report endpoints beyond the existing missing-timesheets
  API export flow
- new report access for `PROJECT_OWNER` or `PROJECT_MANAGER`
- PDF export

## 3. Notes

- Employee Utilization uses calendar-derived expected capacity inside the
  selected date range.
- Approval Turnaround includes both completed and pending approval items and
  flags stalled pending rows by elapsed age.

## 4. Validation

- report cards appear only for `TS_ADMIN`
- filters narrow rows without widening scope
- CSV export matches the filtered HTML rows
- export is audited
