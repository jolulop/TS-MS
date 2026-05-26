# Business Rules Catalog v8.0

## 1. Identity And Access

- External validation is used only to validate the email at access time.
- Production external validation supplies a trusted email claim through the
  configured provider adapter; development email entry is not valid in
  production mode.
- Internal authorization uses employee record, roles, Office, and Business Unit scope.
- Deny by default.
- Row-level scope must be enforced in the database query path where possible.

## 2. Office And Business Unit Rules

- Every Office belongs to one Country.
- Country code and Country name must each be unique.
- One Country can have several Offices.
- Every Business Unit belongs to one Office.
- Business Unit code must be unique within its Office.
- Business Unit operational configuration is inherited from Office configuration.
- `Enable Copy Previous Week` is an Office-level inherited switch.
- Business Unit detail may display inherited configuration but may not edit it.
- Office create/edit must select an existing Country.
- Office creation must also create an initial Business Unit and Office admin employee.
- Office deletion is guarded. It may remove only setup-only bootstrap records
  created to make a new Office manageable: the initial Business Unit, the
  initial Office administrator employee, Office configuration, and audit-only
  references. Operational dependencies still block deletion.

## 3. Employee Rules

- Every employee belongs to one Office.
- Every employee has exactly one primary Business Unit.
- Primary Business Unit must also be in the employee’s Business Unit scope.
- Active `TS_ADMIN` employees must keep full Business Unit scope for their Office, and new Office Business Units extend that scope automatically.
- Business Unit scope changes must be audited.
- Cross-Office employee transfer uses archive-and-recreate instead of mutating
  the existing employee Office.
- The source employee record keeps historical ownership of old timesheets,
  approvals, and audit trail.
- The source employee email must be rewritten to an archival email before the
  real login email can be reused by the new target-Office record.
- The source employee code remains on the historical record; the target record
  requires a new unique employee code.
- `TS_ADMIN_MASTER` is the only role allowed to execute cross-Office employee
  transfer.
- Employee transfer is blocked while the source employee still has active
  operational dependencies such as open timesheets, direct reports, active
  project responsibilities, active project assignments, active General Charge
  Code approval-role memberships, or pending approval items.

## 4. Classification Master Rules

### Clients

- Clients are Office-level.
- Parent Client must belong to the same Office.

### Cost Centers

- Cost Centers are Office-level.

### Pricing Models

- Pricing Models are Office-level.
- Pricing Model name and description are the only business fields.

### Internal Categories

- Internal Categories are Business Unit-level.

### General Charge Codes

- General Charge Codes are Business Unit-level.
- Each General Charge Code must reference a Cost Center from the same active Office.
- `Common Code` is not part of the current General Charge Code model.
- Validity windows and behavior flags are enforced in the domain layer.
- If `Requires Approval` is enabled, the General Charge Code must keep at least one
  configured approver role.
- Configured approver roles can point to:
  - existing TS internal roles
  - office-scoped ad-hoc General Charge Code approval roles
- A selected ad-hoc General Charge Code approval role must be active and must keep
  at least one active member employee.
- An ad-hoc General Charge Code approval role that is already referenced by one or
  more General Charge Codes cannot be set inactive and cannot lose all active
  members.

## 5. Calendar Rules

- Yearly Calendars are Office-level inside the active Office.
- A Yearly Calendar can remain active outside its calendar year.
- Only one Yearly Calendar can exist for a given year in an Office.
- Employee time entry requires an assigned Office calendar.
- If an active employee in an active Office has no assigned calendar and the
  Office has an eligible active calendar, employee-management flows and
  compatibility backfill assign that Office calendar automatically.
- Calendar Period Rules are Business Unit-level inside the shared Office Yearly Calendar.
- Calendar Period Rules may overlap across different Business Units, but not within the same Business Unit and Yearly Calendar.
- If an employee's assigned Office calendar has rules for exactly one Business
  Unit pattern and the employee's current primary Business Unit has no matching
  rules yet, the system may clone that rule pattern into the employee's primary
  Business Unit to keep timesheet validation operable.
- Weekends are non-working by default.
- `working_on_saturdays_flag` and `working_on_sundays_flag` make those weekend days chargeable for the matching Business Unit period.
- `saturday_max_hours` and `sunday_max_hours` define the daily limit for enabled weekend working days.
- Daily limit validation always counts all charged time for the date, including
  billable and non-billable time. The legacy Office
  `count_non_billable_in_daily_limit_flag` is retained for compatibility but is
  not user-editable in the UI.
- Active Special Days override working weekends and remain non-working.
- Calendar Special Day date must belong to the selected Yearly Calendar year.
- Only one Calendar Special Day can exist per date inside a Yearly Calendar.
- Supported Calendar Special Day types are:
  - `NATIONAL_HOLIDAY`
  - `LOCAL_HOLIDAY`
  - `TIMIA_DAY`
  - `OTHER`

## 6. Project Rules

- Projects belong to one Business Unit and one Office.
- Project Owner is mandatory and must hold `PROJECT_OWNER`.
- Project Manager is mandatory and must hold `PROJECT_MANAGER`.
- Client is mandatory and must belong to the same Office.
- Cost Center is mandatory and must belong to the same Office.
- Pricing Model is mandatory and must belong to the same Office.
- Internal Category is mandatory and must belong to the same Business Unit.
- Project code must be unique within the Business Unit.
- `end_date` must not be before `start_date`.
- `close_date` must not be before `start_date`.
- Closed projects cannot receive new assignments or new time after close.

## 7. Project Assignment Rules

- Assignment employee must be active.
- Assignment employee must be in the project Business Unit scope.
- Assignment date range must stay inside the allowed project window.
- Active normal Project Assignment windows must not overlap another active
  normal Project Assignment or active Cross-Office Staffing window for the
  same employee/project combination.

## 7A. Cross-Office Staffing Rules

- Cross-office staffing is a dedicated model separate from normal Project
  Assignments.
- Same-office staffing is invalid in the cross-office staffing flow.
- Cross-office staffing employee must be active.
- Cross-office staffing date range must stay inside the allowed project window.
- Cross-office staffing must not overlap an active normal Project Assignment or
  another active cross-office staffing window for the same employee and
  project.
- Staffing-window overlap checks must run inside a write-side concurrency guard
  so concurrent active staffing writes for the same employee/project cannot both
  pass validation in production database environments.
- Cross-office staffing create behavior must keep target-project context
  visible:
  - target Project determines the read-only target Office and target Business
    Unit
  - selected Origin Office narrows the eligible employee list to that office
- Cross-office staffing does not change the employee's home Office, home
  Business Unit, calendar, or General Charge Code context.
- Active cross-office staffing blocks employee transfer until the staffing is
  resolved.

## 8. Timesheet Rules

- One employee can have at most one weekly timesheet per week.
- Timesheet week starts on Monday and may include configured working weekend days.
- The personal weekly list shows missing timesheet gaps as synthetic rows for Monday-starting weeks with no record since employee creation.
- The TS Project Management missing-timesheet counter treats only `SUBMITTED`
  or `APPROVED` weekly timesheets as present when evaluating assignment-week
  gaps.
- The project missing-timesheets report shows missing employee weeks only within active project-assignment windows and deduplicates rows by employee and week.
- Employee Utilization expected hours are derived from the employee calendar,
  chargeable working days, weekend-working flags, and active Special Days for
  the selected date range.
- Approval Turnaround uses submission timestamps plus final approval or
  rejection action timestamps to derive elapsed hours for completed items.
- Pending Approval Turnaround rows are considered stalled when they exceed the
  report aging threshold.
- Weekend entry is allowed only when the active Business Unit Calendar Period Rule enables it and no active Special Day overrides it.
- A line charges exactly one target:
  - Project
  - General Charge Code
- Employees can charge a project only when the work date is covered by either:
  - an active normal Project Assignment
  - an active Cross-Office Staffing record
- Employees can charge only valid general charge codes from the weekly-timesheet
  home Business Unit context.
- Origin-office holidays or other non-working Special Days block project
  charging because the employee calendar controls work-date availability.
- Target-office holidays do not block charging by themselves when the
  employee's home-office calendar marks the date as working.
- Origin-office employee administration must still show active cross-office
  staffed projects as read-only project visibility.
- Office / BU Time Summary is project-line based:
  - General Charge Code lines do not produce summary rows
  - origin-office admins can still see cross-office project hours when the
    weekly-timesheet home BU is in scope
  - target-office admins can see outside-employee project hours when the
    charged project's BU is in scope
  - displayed Office / Business Unit attribution for cross-office project rows
    follows the charged project, not the employee's home BU
- Approved timesheets are locked.
- Archived timesheets are not editable.
- A draft timesheet can be deleted only when it has no submission-cycle
  history. If the timesheet was ever submitted, later withdraw restores the
  editable `CREATED` status but does not restore deletability.

## 9. Approval Rules

- Project Owners may review approval items for owned projects in the approval
  worklist but do not gain approve or reject authority from ownership alone.
- Project approval items route to the assigned Project Manager.
- Project approval routing is based on the target project even when the charged
  employee belongs to another Office.
- General Charge Code approval items route to a snapped set of approver roles.
- Any active employee matching one of those snapped roles can act on the General Charge
  Code approval item, and the first decision wins.
- An approver cannot approve their own submitted timesheet as the acting approver for that item.
- `TS_ADMIN` oversight follows:
  - target project Office and scoped target Business Unit for project approval
    items
  - weekly-timesheet home Business Unit for General Charge Code approval items

## 10. Period Lock And Retention Rules

- Office Approval Mode currently supports only `PROJECT` in implemented
  timesheet submission behavior. Legacy `LINE` and `MIXED` reference values are
  retained for compatibility but are hidden from Office configuration screens.
- Office `timesheet_cutoff_date` locks older employee edits/submissions by
  Business Unit inheritance when configured outside the Office HTML UI. It is
  retained for compatibility but is not user-editable in Office or Business
  Unit configuration screens.
- `TS_ADMIN` may override a specific lock with audit.
- Retention/archive behavior is driven by Office configuration.
- `Enable Timer` and `Enable Leave Integration` are retained as reserved Office
  compatibility switches and are not user-editable in Office or Business Unit
  configuration screens.
- `Copy Prev. Week` may only use the employee's most recent approved earlier
  timesheet as the source.
- copied lines must still pass the normal validation rules of the target week.

## 11. Delete Rules

- Administrative deletes are guarded by referential integrity.
- No cascade business deletion is performed from UI delete actions.
- When a dependency exists, the system must block the delete and show an error.
- Standard System Management detail screens place delete as a separate bottom action.

## 12. Audit Rules

Audit is required for:
- employee identity changes
- role changes
- Business Unit scope changes
- project owner/manager changes
- project staffing changes, including Cross-Office Staffing
- timesheet line replacement, recorded as a weekly-timesheet summary with
  before/after line count and total hours
- timesheet submit, withdraw, reopen, archive, restore
- approval approve/reject
- guarded administrative deletes
- project missing-timesheets report generation
- project missing-timesheets CSV export
- project-time CSV export
- pending-approvals CSV export
- archived-timesheets CSV export
- audit-history CSV export
- integration-jobs CSV export
- audit events can include an optional correlation identifier supplied by the
  caller
- employee-utilization CSV export
- office-bu-time-summary CSV export
- general-charge-code-usage CSV export
- approval-turnaround CSV export

## 13. Azure Development Rules

- Azure development environments must use the production authentication
  boundary with Google SSO / trusted-header ingress.
- Azure development environments must use PostgreSQL-compatible database
  configuration; SQLite is local-only.
- Reference data and dev sample data seed commands must remain idempotent so
  they can be rerun safely during migration validation.
- Historical migration compatibility fixes must preserve already-applied data
  and must not weaken the logical Country, Office, and seed-data constraints.
