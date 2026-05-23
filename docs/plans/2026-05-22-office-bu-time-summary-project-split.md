# Office / BU Time Summary Project Split

## Goal

Rework `Reports > Office / BU Time Summary` so the grid summarizes project
time by project for the selected period and Business Unit context while still
handling cross-office staffing correctly for both:

- origin-office admins reviewing their employees' time
- target-office admins reviewing their projects' time

## Scope

- keep the existing report entry point, filters, CSV export, and stacked layout
- change the grid from BU-only aggregation to project-split aggregation
- limit the summary rows to project-charged lines
- make cross-office project time visible from either office perspective:
  - home-office / home-BU attribution when the viewer scope contains the
    weekly-timesheet BU
  - target-project Office / target-project BU attribution when the viewer
    scope contains the project BU but not the home BU

## Assumptions

- Add a `Project` column even though the request did not list it explicitly,
  because project-split rows need a project identifier to be usable.
- `Employees`, `Timesheets`, and `Lines` are derived from the selected-period
  project time rows, not from the staffing tables.
- General Charge Code lines do not appear in this report once it becomes
  project-split.

## Implementation Notes

- use one project-line queryset with effective Office / BU annotations based on
  the viewer's scoped BU set
- keep home-BU attribution precedence when a line is visible from both home and
  target perspectives
- update CSV export and UI/docs/tests together so the new semantics stay clear

## Validation

- update focused report tests for:
  - new headers
  - project grouping
  - origin-office cross-office visibility
  - target-office cross-office visibility
  - CSV header/content
