# Use Cases And Acceptance v6.1

## 1. Country Management

### Use Case

`TS_ADMIN_MASTER` creates, updates, and guarded-deletes Countries used by Offices.

### Acceptance

- Country create requires unique Country code and Country name
- Country detail allows status updates
- guarded delete succeeds when no Office references the Country
- guarded delete fails when one or more Offices still reference the Country

## 2. Office Bootstrap

### Use Case

`TS_ADMIN_MASTER` creates a new Office and makes it immediately manageable.

### Acceptance

- Office collection shows active employee count per Office
- Office collection uses a standalone `Create Office` action instead of an inline create form
- Office creation requires selecting an existing Country
- Office is created
- Office configuration is created
- bootstrap Business Unit is created in that Office
- bootstrap admin employee is created in that Office
- bootstrap admin employee is assigned to the bootstrap Business Unit

## 3. Office Configuration Inheritance

### Use Case

`TS_ADMIN_MASTER` updates Office configuration and Business Units inherit it.

### Acceptance

- Office detail allows configuration edit
- Business Unit detail shows inherited values read-only
- timesheet runtime behavior reads the inherited values

## 3A. Employee Office Transfer

### Use Case

`TS_ADMIN_MASTER` transfers a real person from one Office to another without
rewriting source-office history.

### Acceptance

- the transfer is launched from a dedicated master-only `Employee Transfer`
  screen
- the admin first selects an active source employee
- the screen shows source summary and transfer-readiness details
- the transfer is blocked while active operational dependencies still point to
  the source employee
- active cross-office staffing is one of the transfer blockers
- success archives the source employee email
- success sets the source employee to `INACTIVE`
- success closes active source roles and Business Unit scope
- success creates a new active target-Office employee record with:
  - a new unique employee code
  - the selected target Office
  - the selected target primary Business Unit
  - the selected target Business Unit scope
  - the selected target roles
  - the real login email from the source record
- source historical records remain attached to the source employee record

## 3B. Copy Previous Week

### Use Case

An employee creates a new weekly timesheet by copying the most recent approved
earlier timesheet when the parent Office enables the feature.

### Acceptance

- `My Timesheets` shows `Copy Prev. Week` only when the Office configuration
  flag is enabled
- the employee selects a target Monday week start and triggers the copy action
- the system uses the employee's most recent approved earlier timesheet as the
  copy source
- the new weekly timesheet is created in `CREATED` status
- copied lines are shifted into the target week by weekday
- copied lines still obey normal backend validation for accessible charge
  targets, working days, and daily limits
- if no approved earlier timesheet exists, the action fails with a user-facing
  error

## 4. Client Management

### Use Case

`TS_ADMIN` creates and updates Office-level Clients.

### Acceptance

- Client creation does not require a Business Unit
- Client belongs to active Office
- Parent Client, if present, is in the same Office
- Client collection shows one row per Business Unit where the client has active
  projects
- each client row shows the active-project count and active-assigned-employee
  count for that specific Business Unit row
- clicking the project count redirects to `Project Management` only when the
  caller is assigned to the row Business Unit; otherwise the screen shows an
  authorization error
- collection rows open Client detail from the primary item link without a visible action column
- Client edit uses the same standalone layout pattern as Client creation, with delete at the bottom

## 5. Cost Center Management

### Use Case

`TS_ADMIN` creates and updates Office-level Cost Centers.

### Acceptance

- Cost Center creation does not require a Business Unit
- Cost Center belongs to active Office
- collection rows open Cost Center detail from the primary item link without a visible action column
- Cost Center edit uses the same standalone layout pattern as Cost Center creation, with delete at the bottom

## 6. Pricing Model Management

### Use Case

`TS_ADMIN` maintains Pricing Models for the active Office.

### Acceptance

- create Pricing Model with name and description
- update Pricing Model
- guarded delete succeeds when no project references exist
- guarded delete fails when a project still references the Pricing Model
- collection rows open Pricing Model detail from the primary item link without a visible action column
- Pricing Model edit uses the same standalone layout pattern as Pricing Model creation, with delete at the bottom

## 7. Calendar Management

### Use Case

`TS_ADMIN` manages a Yearly Calendar and its Special Days inside System Management.

### Acceptance

- create Yearly Calendar inside the active Office without assigning a Business Unit
- open Calendar detail and browse the month view
- create Calendar Period Rules by selecting a Business Unit inside the shared Office calendar
- allow overlapping Calendar Period Rules for different Business Units
- reject overlapping Calendar Period Rules inside the same Business Unit
- save Working On Saturdays and Working On Sundays flags plus their max-hours on a Calendar Period Rule
- delete Calendar Period Rules when no protected references exist
- create Special Day with date and type
- update Special Day date or type
- delete Special Day when no protected references exist
- guarded delete fails with an error when a Calendar still has protected dependencies
- Calendar collection rows open detail from the primary item link without a visible action column
- Calendar edit uses the same standalone layout direction as creation, with delete at the bottom

## 8. Project Creation

### Use Case

`TS_ADMIN` creates a new Project.

### Acceptance

- Pricing Model is mandatory
- Project Owner must hold `PROJECT_OWNER`
- Project Manager must hold `PROJECT_MANAGER`
- Client belongs to the same Office
- Cost Center belongs to the same Office
- Pricing Model belongs to the same Office
- Internal Category belongs to the same Business Unit

### Additional Acceptance

- guarded delete succeeds when no assignments, timesheet lines, approval items, or other protected references exist
- guarded delete fails when dependent records still reference the Project
- collection rows open Project detail from the primary item link without a visible action column
- Project edit uses the same standalone layout pattern as Project creation, with delete at the bottom

## 9. Project Assignment Creation

### Use Case

`TS_ADMIN` assigns an employee to a Project.

### Acceptance

- employee is active
- employee is in project Business Unit scope
- project is not closed
- assignment window respects project dates
- collection rows open Project Assignment detail from the primary item link without a visible action column
- Project Assignment edit uses the same standalone layout pattern as Project Assignment creation, with delete at the bottom

### Additional Acceptance

- guarded delete succeeds when no protected references exist

## 9A. Cross-Office Staffing Management

### Use Case

`TS_ADMIN`, `PROJECT_OWNER`, or `PROJECT_MANAGER` staffs an employee from one
Office into a project owned by another Office without transferring the
employee.

### Acceptance

- the target project and employee belong to different Offices
- same-office attempts are rejected in the Cross-Office Staffing flow
- employee is active
- project is not closed
- when only one eligible target project exists, the create screen preloads it
  and shows Target Office and Target BU immediately
- selecting Origin Office narrows the employee choices to that office only
- staffing window respects project dates
- overlapping active staffing windows across normal Project Assignments and
  Cross-Office Staffing are rejected
- `TS_ADMIN` can create, edit, and delete cross-office staffing for scoped
  target projects
- `PROJECT_OWNER` can create, edit, and delete cross-office staffing only for
  owned target projects
- `PROJECT_MANAGER` can create, edit, and delete cross-office staffing only
  for managed target projects

## 8A. General Charge Code Management

### Use Case

`TS_ADMIN` maintains General Charge Codes in scoped Business Units.

### Acceptance

- create and update a General Charge Code with mandatory Cost Center, lifecycle, and validity fields
- require at least one approver role when `Requires Approval` is enabled
- reject ad-hoc approver-role selection when the selected ad-hoc role has no active
  member employees or is inactive
- reject create or edit when Cost Center is empty
- guarded delete succeeds when no timesheet lines, approval items, or other protected references exist
- guarded delete fails when dependent records still reference the General Charge Code
- collection rows open General Charge Code detail from the primary item link without a visible action column
- General Charge Code edit uses the same standalone layout pattern as General Charge Code creation, with delete at the bottom

## 8B. General Charge Code Approval Role Management

### Use Case

`TS_ADMIN` maintains office-scoped ad-hoc approval roles used only for General Charge Code approvals.

### Acceptance

- create and update an ad-hoc approval role with member employees from the active Office
- existing TS internal roles are selectable on General Charge Codes but are not editable in this screen
- show active member count, dependent General Charge Code count, and routing coverage
  status in the admin views and API
- reject setting a referenced ad-hoc approval role to `INACTIVE`
- reject removing all active member employees from a referenced ad-hoc approval role
- guarded delete fails when General Charge Codes or approval history still reference the ad-hoc role
- collection rows open GCC Approval Role detail from the primary item link without a visible action column
- GCC Approval Role edit uses the same standalone layout pattern as GCC Approval Role creation, with delete at the bottom

## 9. Employee Self-Service Timesheet

### Use Case

An authenticated employee edits and submits a weekly timesheet.

### Acceptance

- only one timesheet exists per employee/week
- lines are limited to chargeable working dates for the week
- weekend lines are allowed only when the active Business Unit Calendar Period Rule enables them
- weekend daily limits use the configured Saturday/Sunday max-hours from the active Calendar Period Rule
- active Special Days override working weekends and remain non-working
- line target is Project xor General Charge Code
- submit is blocked when validation fails
- the personal list shows current, historical, and missing weekly rows in one screen
- the personal list includes `Status`, `Week Start From`, and `Week Start To` filters
- missing weekly rows are derived from Monday-starting gaps since employee record creation
- selecting a missing week preloads the create controls for that week

## 9A. Employee And Scoped Master Edit Layout

### Use Case

`TS_ADMIN` edits existing scoped System Management records using the same visual layout as creation.

### Acceptance

- Employee detail removes the current-state panel
- Employee detail shows core data in one row, with role assignment and Business Unit scope below
- Business Unit, Internal Category, Calendar Period Rule, Client, Cost Center, Pricing Model, Project, Project Assignment, GCC Approval Role, and General Charge Code detail screens use the same standalone create/edit layout direction
- delete is placed at the bottom of those detail screens as a separate action

## 10. Approval Workflow

### Use Case

An eligible approver processes routed approval items.

### Acceptance

- approval worklist is visible to:
  - `PROJECT_MANAGER` for directly assigned project approvals
  - any employee matching the configured roles on a General Charge Code approval item
- only assigned project items or role-matched General Charge Code items are actionable
- General Charge Code approval uses first-decision-wins behavior
- approve and reject actions are audited

## 11. Project Time Inquiry

### Use Case

A Project Owner or Project Manager views live project time.

### Acceptance

- inquiry screen is available to `PROJECT_OWNER` and `PROJECT_MANAGER`
- only owned or managed project scope is visible

## 11A. Project Management Summary

### Use Case

`TS_ADMIN`, `PROJECT_OWNER`, or `PROJECT_MANAGER` opens the TS Project
Management summary.

### Acceptance

- status filters support `All`, `Active`, `Closed`, and `Draft`
- rows show project name, status, approved hours, pending submitted
  timesheets, and missing timesheets
- staffing-derived project values include both normal Project Assignments and
  Cross-Office Staffing
- `TS_ADMIN` can open the project detail screen from the project name
- `PROJECT_OWNER` can open owned-project detail in editable System Management
  mode from the project name
- `PROJECT_MANAGER` does not get the project-name detail link
- approved-hours drill-down opens the project-time report preloaded to the
  selected project
- pending-timesheet drill-down opens the approval worklist for owned projects
- missing-timesheet drill-down opens the missing-timesheets report preloaded to
  the selected project

## 12A. Personal Timesheet Delete Guard

### Use Case

An employee tries to delete a weekly timesheet after earlier submit/withdraw
activity.

### Acceptance

- a pure draft timesheet with no submission history can be deleted
- a submitted timesheet cannot be deleted
- a withdrawn timesheet that returned to `CREATED` but still has submission
  cycles remains non-deletable

## 11C. Project Owner System Management

### Use Case

`PROJECT_OWNER` manages owned projects and owned-project assignments from System
Management.

### Acceptance

- `PROJECT_OWNER` can open `System Management > Projects` and
  `System Management > Project Assignments`
- project create is available and the saved project owner is always the current
  employee profile
- `PROJECT_OWNER` can select the project manager and may select themself when
  they also hold `PROJECT_MANAGER`
- `PROJECT_OWNER` can edit and delete only owned projects
- `PROJECT_OWNER` can create, edit, and delete assignments only for owned
  projects
- out-of-scope projects and assignments remain blocked server-side

## 11E. Project Collection And Assignment Filtering

### Use Case

`TS_ADMIN` refines `Project Management` and `Project Assignment Management`
collections using the new project- and client-related filters and drill-downs.

### Acceptance

- `Project Management` shows Business Unit name, Client, owner full name,
  manager full name, and employee assignment counts
- project employee assignment counts include both normal Project Assignments
  and Cross-Office Staffing
- `Project Management` supports an inline Client filter that preserves the
  selected Project Status
- clicking a project employee-count cell opens `Project Assignment Management`
  prefiltered to that project with `status=All`
- `Project Assignment Management` shows Client and Project Name columns
- `Project Assignment Management` supports a dependent Client -> Project filter
  pair
- changing the Client filter clears the selected Project filter automatically

## 11D. Project Manager System Management

### Use Case

`PROJECT_MANAGER` manages assignments for managed projects from System
Management.

### Acceptance

- `PROJECT_MANAGER` can open `System Management > Project Assignments`
- `PROJECT_MANAGER` can create, edit, and delete assignments only for managed
  projects
- unmanaged project assignments remain blocked server-side

## 11F. TS Project Management Summary

### Use Case

An authorized `TS_ADMIN`, `PROJECT_OWNER`, or `PROJECT_MANAGER` uses the
`TS/Project Management > Project Management` summary screen to filter projects
and drill into related approval and reporting work.

### Acceptance

- the summary grid shows `Client` between `Name` and `Status`
- the top filter row includes an inline `Client` selector to the left of the
  status-filter buttons
- changing the Client filter preserves the selected status filter
- nonzero `Pend. Appr.` values open the Approval Worklist prefiltered to the
  selected project
- zero `Pend. Appr.` values remain plain text

## 11B. Project Missing Timesheets Report

### Use Case

`PROJECT_OWNER`, `PROJECT_MANAGER`, or `TS_ADMIN` runs a project-scoped missing-timesheets report and exports the result to CSV.

### Acceptance

- `PROJECT_OWNER` can multi-select from owned projects only
- `PROJECT_MANAGER` can multi-select from managed projects only
- users holding both roles can multi-select from the union of owned and managed projects
- `TS_ADMIN` can multi-select from projects visible in current Office and Business Unit scope
- rows show project name, employee name, employee email, and missing timesheet week start date
- missing weeks are limited to the assigned project scope and are deduplicated by employee and week
- project staffing windows include both normal Project Assignments and
  Cross-Office Staffing
- UI export downloads a CSV attachment directly
- API export creation returns a CSV download URI
- report generation is audited
- CSV export is audited

## 11BA. Existing Report CSV Exports

### Use Case

An authorized user exports one of the existing operational reports from the
report viewer without copying rows manually from the browser.

### Acceptance

- Project Time can be exported to CSV from the report viewer
- Pending Approvals can be exported to CSV from the report viewer
- Archived Timesheets can be exported to CSV from the report viewer
- Audit History can be exported to CSV from the report viewer
- Integration Jobs can be exported to CSV from the report viewer
- Employee Utilization can be exported to CSV from the report viewer
- Office / BU Time Summary can be exported to CSV from the report viewer
- General Charge Code Usage can be exported to CSV from the report viewer
- Approval Turnaround can be exported to CSV from the report viewer
- each CSV export uses the currently selected filters
- each CSV export keeps the same server-side authorization and row scope as the
  visible report grid
- each CSV export is audited
- Missing Timesheets by Project keeps its existing API export flow in addition
  to the UI export

## 11BB. Advanced TS Admin Reports

### Use Case

`TS_ADMIN` runs deeper operational analytics inside the current active Office
and scoped Business Units.

### Acceptance

- Reports Hub shows these additional reports for `TS_ADMIN` only:
  - `Employee Utilization`
  - `Office / BU Time Summary`
  - `General Charge Code Usage`
  - `Approval Turnaround`
- Reports Hub keeps `Archived Timesheets`, `Audit History`, and
  `Integration Jobs` at the bottom of the admin card list
- `PROJECT_OWNER` and `PROJECT_MANAGER` do not gain access to these four admin
  reports from this change
- Employee Utilization supports filters for Business Unit, employee, and
  work-date range and shows expected hours, worked hours, billable split, and
  utilization percent
- Office / BU Time Summary supports filters for Business Unit and work-date
  range and aggregates project-charged employee count, timesheet count, lines,
  and hour totals by project
- Office / BU Time Summary excludes General Charge Code-only rows
- Office / BU Time Summary includes project-charged cross-office employee time
  for both:
  - origin-office admin reporting through the weekly-timesheet home Office /
    Business Unit
  - target-office admin reporting through the charged project's Office /
    Business Unit
- Office / BU Time Summary displays cross-office project rows with the charged
  project's Office and Business Unit values, not the employee's home ones
- General Charge Code Usage supports filters for Business Unit, General Charge
  Code, employee, and work-date range and aggregates usage totals by code
- Approval Turnaround supports filters for Business Unit, project, approver,
  status, and submitted-date range
- Approval Turnaround shows both completed and pending rows, including elapsed
  hours and stalled-age visibility
- the shared report viewer stacks the `Filter Panel` above `Report Totals` for
  the supported report screens
- all four reports support CSV export from the shared report viewer
- each export uses the same filters and scope as the visible grid
- each export is audited

## 11BC. Cross-Office Time-Entry And Project Reporting

### Use Case

An employee staffed from one Office to another Office's project enters time
and the target project stakeholders review the result.

### Acceptance

- the employee uses the employee's home-office calendar and calendar period
  rules
- the employee uses the employee's home-office General Charge Codes
- if the employee's home-office calendar marks the date as holiday or other
  non-working Special Day, the employee cannot charge the target-office
  project
- if the target-office calendar marks the date as holiday but the employee's
  home-office calendar marks the date as working, the target-office holiday
  alone does not block charging
- project approval visibility follows the target project even when the charged
  employee belongs to another Office
- `Project Time` includes the charged project time from cross-office staffed
  employees

## 11C. TS Admin Approval Worklist

### Use Case

`TS_ADMIN` opens the approval workspace to monitor pending approvals across the
active Office and scoped Business Units without taking over the approver role.

### Acceptance

- `TS_ADMIN` can open `/approvals/` and see pending approval items in scoped
  scope
- the `Approval Worklist` title is shared with the approver-facing workspace
- the oversight UI shows employee name, target, Business Unit, approver name,
  TS submission date, pending age, and stalled-state context
- filters support search, Business Unit, employee, project, target type, and
  aging
- on desktop, the six oversight filters render as three items per row across
  two rows
- `TS_ADMIN` can open approval detail in read-only mode
- approval detail shows a compact top context row and the related links box
  below it
- approval detail links to the related timesheet and project
- `TS_ADMIN` does not gain approve/reject authority from this screen alone
- related timesheet detail exposes the existing admin exception actions:
  reopen, admin withdraw to `SUBMITTED`, archive, and restore
- related timesheet detail shows `Submitted At` and `Approved At` using
  short-date formatting
- oversight visibility remains constrained to active Office and Business Unit
  scope server-side
- project approval items follow the target project Office and scoped target
  Business Unit
- General Charge Code approval items remain scoped by the weekly-timesheet
  home Business Unit

## 12. Guarded Deletes

### Use Case

An admin deletes a transient master record from System Management.

### Acceptance

- delete succeeds when no protected references exist
- delete fails with an error when references still exist
- no cascade business delete occurs

## 13. TS Admin Business Unit Scope Synchronization

### Use Case

`TS_ADMIN` scope stays aligned with all Business Units in the active Office so Business Units cannot become orphaned.

### Acceptance

- creating a new Business Unit assigns it to every active `TS_ADMIN` employee in the same Office
- creating an employee with `TS_ADMIN` assigns all Business Units in that Office to the employee scope
- adding `TS_ADMIN` to an existing employee expands the employee scope to all Business Units in that Office
- saving Business Unit scope for an employee who still has `TS_ADMIN` may change the primary Business Unit but keeps the full Office Business Unit scope

## 14. Business Unit Code Reuse Across Offices

### Use Case

`TS_ADMIN` creates a Business Unit in one Office using a code that already exists in a different Office.

### Acceptance

- creation succeeds when the duplicate code exists only in another Office
- creation fails when the duplicate code already exists in the active Office
