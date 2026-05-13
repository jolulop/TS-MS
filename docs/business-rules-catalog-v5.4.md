# Business Rules Catalog v5.4

## 1. Identity And Access

- External validation is used only to validate the email at access time.
- Internal authorization uses employee record, roles, Office, and Business Unit scope.
- Deny by default.
- Row-level scope must be enforced in the database query path where possible.

## 2. Office And Business Unit Rules

- Every Business Unit belongs to one Office.
- Business Unit code must be unique within its Office.
- Business Unit operational configuration is inherited from Office configuration.
- Business Unit detail may display inherited configuration but may not edit it.
- Office creation must also create an initial Business Unit and Office admin employee.

## 3. Employee Rules

- Every employee belongs to one Office.
- Every employee has exactly one primary Business Unit.
- Primary Business Unit must also be in the employee’s Business Unit scope.
- Active `TS_ADMIN` employees must keep full Business Unit scope for their Office, and new Office Business Units extend that scope automatically.
- Business Unit scope changes must be audited.

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

## 5. Calendar Rules

- Yearly Calendars are Office-level inside the active Office.
- A Yearly Calendar can remain active outside its calendar year.
- Only one Yearly Calendar can exist for a given year in an Office.
- Calendar Period Rules are Business Unit-level inside the shared Office Yearly Calendar.
- Calendar Period Rules may overlap across different Business Units, but not within the same Business Unit and Yearly Calendar.
- Weekends are non-working by default.
- `working_on_saturdays_flag` and `working_on_sundays_flag` make those weekend days chargeable for the matching Business Unit period.
- `saturday_max_hours` and `sunday_max_hours` define the daily limit for enabled weekend working days.
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

## 8. Timesheet Rules

- One employee can have at most one weekly timesheet per week.
- Timesheet week starts on Monday and may include configured working weekend days.
- Weekend entry is allowed only when the active Business Unit Calendar Period Rule enables it and no active Special Day overrides it.
- A line charges exactly one target:
  - Project
  - General Charge Code
- Employees can charge only valid scoped projects or valid general charge codes.
- Approved timesheets are locked.
- Archived timesheets are not editable.

## 9. Approval Rules

- Approval worklist is currently a `PROJECT_MANAGER` workflow.
- A Project Manager can act only on approval items assigned to them.
- An approver cannot approve their own submitted timesheet as the acting approver for that item.

## 10. Period Lock And Retention Rules

- Office `timesheet_cutoff_date` locks older employee edits/submissions by Business Unit inheritance.
- `TS_ADMIN` may override a specific lock with audit.
- Retention/archive behavior is driven by Office configuration.

## 11. Delete Rules

- Administrative deletes are guarded by referential integrity.
- No cascade business deletion is performed from UI delete actions.
- When a dependency exists, the system must block the delete and show an error.

## 12. Audit Rules

Audit is required for:
- employee identity changes
- role changes
- Business Unit scope changes
- project owner/manager changes
- timesheet submit, withdraw, reopen, archive, restore
- approval approve/reject
- guarded administrative deletes
