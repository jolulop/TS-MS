# Copy Previous Week

## 1. Goal

Turn the Office-level `Enable Copy Previous Week` configuration flag into a real
user-initiated feature on `My Timesheets`, while leaving `Enable Timer` and
`Enable Leave Integration` inactive.

## 2. Scope

In scope:
- Office-gated `Copy Prev. Week` action on `My Timesheets`
- copy source limited to the employee's most recent approved timesheet
- create the selected week and preload copied lines
- copied lines must still pass the normal backend charge-target, working-day,
  and daily-limit validations
- tests and current v5.7 docs

Out of scope:
- timer-based time capture
- leave or absence integration
- automatic background copying without user action

## 3. Source Documents

- `docs/functional-spec-v5.7.md`
- `docs/ui-screen-spec-v5.7.md`
- `docs/use-cases-acceptance-v5.7.md`
- `docs/authorization-matrix-v5.7.md`
- `AGENTS.md`

## 4. Design

- keep the existing week-start picker on `My Timesheets`
- add a second submit action: `Copy Prev. Week`
- gate the button by the Office configuration flag
- when used:
  - create the selected weekly timesheet
  - find the employee's latest approved timesheet before the selected week
  - shift copied line dates by weekday offset into the new week
  - reuse the normal line-validation service flow

## 5. Risks

- copied lines must not bypass project assignment, GCC validity, weekend, or
  daily-limit validation
- duplicate target-week protection must stay unchanged
- missing approved source should fail clearly instead of creating misleading
  empty copies
