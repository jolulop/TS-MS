# Cross-Office Staffing Follow-Up

## Scope

Address three follow-up gaps found during UAT:

1. `System Management > Cross-Office Staffing > Create`
   - target project context should fill `Target Office` and `Target BU`
   - selecting `Origin Office` should narrow the employee list to that office
2. `System Management > Employees > Employee Detail`
   - the read-only project assignment box should include cross-office staffed
     projects so the employee project picture is complete
3. `Reports > Office / BU Time Summary`
   - cross-office employee time must be visible in admin reporting without
     losing either the origin-office or target-office perspective

## Implementation Notes

- Keep create-form enforcement server-side:
  - project scope remains target-office scoped
  - employee selection must still match the selected origin office
- Improve the create-form UX with dependent project and origin-office context in
  the browser.
- Keep employee detail read-only for cross-office rows; do not make them
  editable from the employee screen.
- The later project-split refinement may evolve this report beyond the original
  home-BU-only summary if it preserves both office perspectives clearly.

## Validation

- extend focused `System Management` tests for the create screen and employee
  detail
- add report coverage for cross-office time in `Office / BU Time Summary`
