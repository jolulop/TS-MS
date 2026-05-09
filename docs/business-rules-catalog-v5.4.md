# Business Rules Catalog v5.4

## 1. Identity And Access

- External validation is used only to validate the email at access time.
- Internal authorization uses employee record, roles, Office, and Business Unit scope.
- Deny by default.
- Row-level scope must be enforced in the database query path where possible.

## 2. Office And Business Unit Rules

- Every Business Unit belongs to one Office.
- Business Unit operational configuration is inherited from Office configuration.
- Business Unit detail may display inherited configuration but may not edit it.
- Office creation must also create an initial Business Unit and Office admin employee.

## 3. Employee Rules

- Every employee belongs to one Office.
- Every employee has exactly one primary Business Unit.
- Primary Business Unit must also be in the employee’s Business Unit scope.
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
- Validity windows and behavior flags are enforced in the domain layer.

## 5. Project Rules

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

## 6. Project Assignment Rules

- Assignment employee must be active.
- Assignment employee must be in the project Business Unit scope.
- Assignment date range must stay inside the allowed project window.

## 7. Timesheet Rules

- One employee can have at most one weekly timesheet per week.
- Timesheet week is Monday to Friday.
- Weekend entry is not supported in the standard editor.
- A line charges exactly one target:
  - Project
  - General Charge Code
- Employees can charge only valid scoped projects or valid general charge codes.
- Approved timesheets are locked.
- Archived timesheets are not editable.

## 8. Approval Rules

- Approval worklist is currently a `PROJECT_MANAGER` workflow.
- A Project Manager can act only on approval items assigned to them.
- An approver cannot approve their own submitted timesheet as the acting approver for that item.

## 9. Period Lock And Retention Rules

- Office `timesheet_cutoff_date` locks older employee edits/submissions by Business Unit inheritance.
- `TS_ADMIN` may override a specific lock with audit.
- Retention/archive behavior is driven by Office configuration.

## 10. Delete Rules

- Administrative deletes are guarded by referential integrity.
- No cascade business deletion is performed from UI delete actions.
- When a dependency exists, the system must block the delete and show an error.

## 11. Audit Rules

Audit is required for:
- employee identity changes
- role changes
- Business Unit scope changes
- project owner/manager changes
- timesheet submit, withdraw, reopen, archive, restore
- approval approve/reject
- guarded administrative deletes
