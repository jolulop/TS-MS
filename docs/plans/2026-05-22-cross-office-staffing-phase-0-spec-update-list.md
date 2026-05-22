# Cross-Office Staffing Phase 0 Spec Update List

## 1. Purpose

This checklist converts the Option 4 implementation blueprint into the
required Phase 0 documentation work before code changes begin.

Phase 0 means:

- update the current source-of-truth specs
- lock the intended behavior for cross-office staffing
- explicitly defer behavior that is not part of the first implementation wave

This checklist assumes the dedicated explicit-model approach defined in:

- [2026-05-22-cross-office-staffing-option-4-blueprint.md](/home/jolulop/code/TS-MS/docs/plans/2026-05-22-cross-office-staffing-option-4-blueprint.md)

## 2. Phase 0 Approval Statement

Before Phase 1 code work starts, the specs must approve these rules:

- a new dedicated `Cross-Office Staffing` concept exists alongside normal
  `Project Assignments`
- same-office staffing continues to use normal `Project Assignments`
- cross-office staffing uses a distinct record type and distinct management UI
- an employee charged to another office's project still uses the employee's
  home-office calendar
- the employee still uses the employee's home-office calendar period rules
- the employee still uses the employee's home-office General Charge Codes
- project approval authority follows the target project, not the employee's
  origin office
- project-time reporting includes all assigned employees regardless of origin
  office
- target-office `TS_ADMIN` approval oversight changes are deferred unless
  explicitly approved as a later phase

## 3. Source-Of-Truth Update Checklist

### 3.1 `docs/specification-index-v6.0.md`

Add an implementation-summary bullet set for the new feature.

Update list:

- add a bullet that System Management will include `Cross-Office Staffing`
- add a bullet that cross-office staffing is modeled separately from normal
  project assignments
- add a bullet that cross-office staffed employees keep home-office
  calendar/GCC semantics
- add a bullet that project approval and project-time visibility follow the
  target project
- add a bullet that target-office `TS_ADMIN` oversight changes are not part of
  the initial baseline unless later approved

### 3.2 `docs/functional-spec-v6.0.md`

This doc needs the largest Phase 0 update.

Update these areas:

- `Section 7. System Management Scope`
  - add `Cross-Office Staffing` to the managed feature list
- `Section 8.2A Employee Transfers`
  - add active cross-office staffing as a transfer blocker
- `Section 8.9 Project Assignments`
  - split into:
    - normal same-office `Project Assignments`
    - dedicated `Cross-Office Staffing`
  - state that same-office staffing remains on the current model
  - state that cross-office staffing does not move the employee into the
    target office
  - state that cross-office staffing management follows target-project scope
- add a new subsection after `8.9` for `Cross-Office Staffing`
  - recommended heading: `8.9A Cross-Office Staffing`
  - define purpose, scope, and lifecycle
  - define immutable identity fields after creation
  - define same-office records as invalid in this flow
  - define overlap blocking against both staffing models
- `Section 9. Timesheet Features`
  - state that project charging eligibility is satisfied by either:
    - active normal assignment
    - active cross-office staffing
  - state that calendar, period-rule, and GCC validation remain based on the
    employee home-office timesheet context
  - state that origin-office holidays block project charging because the
    employee calendar controls work-date availability
  - state that target-office holidays do not block charging by themselves when
    the origin-office calendar marks a working day
- `Section 10. Approval`
  - state that project-office approval covers project time from cross-office
    staffed employees
  - explicitly defer any change to `TS_ADMIN` oversight scope unless later
    approved
- `Section 11. Reports`
  - state that `Project Time Report` includes cross-office staffed employees'
    charged time
  - state that `Missing Timesheets by Project` derives staffing windows from
    both models
  - state that Office/BU summary reports remain based on timesheet/home BU in
    the initial phase

### 3.3 `docs/use-cases-acceptance-v6.0.md`

Add acceptance scenarios that make the intended behavior testable.

Add or update these scenarios:

- `TS_ADMIN` creates a valid cross-office staffing record
- `PROJECT_OWNER` creates a valid cross-office staffing record for an owned
  project
- `PROJECT_MANAGER` creates a valid cross-office staffing record for a managed
  project
- same-office attempt in the cross-office staffing UI is rejected
- overlapping staffing windows across normal and cross-office models are
  rejected
- origin-office holiday blocks project charging for a cross-office staffed
  employee
- target-office holiday does not block charging when the employee home-office
  calendar says the day is working
- project approval worklist includes project time from cross-office staffed
  employees
- `Project Time Report` includes cross-office staffed employees
- `Missing Timesheets by Project` includes cross-office staffing windows
- employee transfer is blocked while active cross-office staffing exists

Recommended additions:

- a dedicated use case for `Cross-Office Staffing Management`
- a focused use case for cross-office time-entry semantics
- a focused use case for cross-office project approval visibility

### 3.4 `docs/data-model-erd-v6.0.md`

Update the logical ERD description to include the new entity.

Update list:

- add `Cross-Office Project Assignments` to the entity inventory
- document relationships to:
  - `Employee`
  - `Project`
  - `Office` as origin office
  - `Business Unit` as origin business unit
  - assignment status reference data
- document the conceptual distinction:
  - `ProjectAssignment` = same-office staffing
  - `CrossOfficeProjectAssignment` = cross-office staffing

### 3.5 `docs/authorization-matrix-v6.0.md`

Add explicit rows for the new management surface and clarify project-based
authority.

Add rows for:

- `Open Cross-Office Staffing`
- `Manage Cross-Office Staffing`
- `Open Cross-Office Staffing Detail`

Recommended access rules:

- `TS_ADMIN`: yes for scoped target projects
- `PROJECT_OWNER`: yes for owned target projects only
- `PROJECT_MANAGER`: yes for managed target projects only
- `USER`: no
- `TS_ADMIN_MASTER`: no direct role grant unless separately desired

Also update notes:

- authority follows target-project scope, not employee origin office
- cross-office staffing does not grant broader employee-management access
- any future target-office `TS_ADMIN` approval oversight expansion is a
  separate authorization change

### 3.6 `docs/ui-screen-spec-v6.0.md`

Add the new UI surfaces and align existing screens that must consume both
staffing models.

Update list:

- `System Management Navigation`
  - add `Cross-Office Staffing`
  - recommended placement: below `Project Assignments`
- add a new screen spec
  - recommended id/title: `SCR-191 Cross-Office Staffing Management`
  - define collection filters, columns, create form, detail form, and scope
- update employee detail UI spec
  - add read-only visibility of active cross-office staffing where relevant
- update `Project Management` UI spec
  - employee counts and staffing drill-downs must count both staffing models
- update report UI specs
  - `Project Time Report` wording should avoid implying that displayed BU is
    always the project BU
  - `Missing Timesheets by Project` should state that both staffing models are
    included

### 3.7 `docs/business-rules-catalog-v6.0.md`

Add the operational rules in compact form.

Update list:

- add a new rule group for `Cross-Office Staffing Rules`
- include:
  - employee must remain active
  - target project must remain active and open for assignment dates
  - same-office records are invalid in the cross-office staffing flow
  - cross-office staffing does not change employee home office, home BU,
    calendar, or GCC context
  - origin-office holiday behavior
  - target-office holiday behavior
  - project approvals follow target project
  - project reporting includes staffed employees regardless of origin office
  - active cross-office staffing blocks employee transfer
- update timesheet rules to state that valid project charging may come from
  either staffing model

## 4. Documents That Likely Need No Phase 0 Change

### 4.1 `docs/integration-api-spec-v6.0.md`

No Phase 0 update is required unless the team decides to expose new `/api/v1`
endpoints for cross-office staffing in the first implementation wave.

If Phase 1 remains server-rendered only, this doc can stay unchanged.

### 4.2 `docs/non-functional-requirements-v6.0.md`

No targeted Phase 0 update is required unless the team wants to add explicit
performance or audit-retention requirements for the new staffing queries.

### 4.3 Existing Advanced Analytics Specs

Do not rewrite Office/BU analytics semantics in Phase 0 unless the business
chooses to shift those reports from home-BU attribution to project-office
attribution.

## 5. Explicit Deferrals To Write Into The Specs

These deferrals should be stated clearly so implementation does not drift:

- `TS_ADMIN` approval oversight remains home-BU scoped in the initial delivery
- `Pending Approvals` and `Approval Turnaround` remain based on
  weekly-timesheet home BU in the initial delivery
- `Office / BU Time Summary`, `Employee Utilization`, and
  `General Charge Code Usage` remain home-BU based in the initial delivery
- normal `Project Assignment Management` and `Cross-Office Staffing`
  management remain separate UIs in the initial delivery
- no new public or JSON API is implied unless separately approved

## 6. Recommended Spec Editing Order

Apply the Phase 0 doc updates in this order:

1. `functional-spec-v6.0.md`
2. `business-rules-catalog-v6.0.md`
3. `authorization-matrix-v6.0.md`
4. `ui-screen-spec-v6.0.md`
5. `use-cases-acceptance-v6.0.md`
6. `data-model-erd-v6.0.md`
7. `specification-index-v6.0.md`

Reason:

- functional behavior first
- condensed business rules second
- access control and UI next
- acceptance and ERD after behavior is stable
- summary index last so it reflects the approved spec set

## 7. Phase 0 Exit Criteria

Phase 0 is complete only when:

- the seven current source-of-truth docs above are updated
- cross-office staffing behavior is described consistently across those docs
- home-office calendar/GCC semantics are explicit
- target-project approval semantics are explicit
- report behavior is explicit about what changes now and what stays deferred
- transfer blocker behavior is explicit
- no unresolved contradiction remains between project-based approval and
  home-BU admin oversight

## 8. Recommended Next Step

After this Phase 0 checklist is approved, the next concrete task should be:

- update the source-of-truth docs themselves

Only after that should Phase 1 code work begin.
