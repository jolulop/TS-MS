# Functional Specification v8.0

## 1. Purpose

Define the approved v8.0 behavior baseline of the Timesheet Management System
after the Office refactor, the expanded System Management feature set, the
latest UI consolidation updates, and the approved cross-office staffing
semantics. The v8.0 baseline also records the first working Azure development
instance with Google SSO ingress and PostgreSQL migration/seed readiness.

## 2. Functional Blocks

The product is split into:
- `System Management`
- `TS Management`

Supporting areas:
- `Approvals`
- `Reports`

## 3. Roles

Supported internal roles:
- `USER`
- `TS_ADMIN`
- `TS_ADMIN_MASTER`
- `PROJECT_OWNER`
- `PROJECT_MANAGER`

Role behavior is additive. A user may hold multiple roles at once.

## 4. Authentication And Session Model

- External validation is used only to validate an email at access time.
- The production authentication boundary is provider-based. The external
  provider supplies a trusted authenticated email claim; TS then resolves that
  email to an internal employee record.
- Local `validated_email` entry is a development adapter only and must be
  disabled when `TSMS_ENVIRONMENT=production`.
- Google SSO or Azure ingress must integrate by passing a trusted email claim
  through the configured production adapter, not by posting arbitrary emails
  from the browser.
- In the Azure development instance, App Service Authentication performs Google
  SSO and forwards the trusted email claim to Django for internal employee,
  role, Office, and Business Unit scope resolution.
- After validation, the system identifies the user internally by `employee.email`.
- The internal session stores the resolved employee and active Office context.
- All later authorization is internal to TS data.
- If the validated email does not resolve to an active employee, access is denied.

### 4.1 Authenticated Shell Navigation

- The authenticated left navigation is organized into:
  - `My info`
  - `TS/Project Management`
  - `System Management`
- `Profile` is part of `My info`.
- `Project Management`, `Approval Worklist`, `Reports`, and `Project Time Inquiry`
  are grouped under `TS/Project Management` with role-aware visibility.
- Employees holding only the basic `USER` role are redirected to `My Timesheets`
  instead of a dashboard and do not see the `Dashboard`, `Reports`, or
  `TS/Project Management` navigation shell.

## 5. Organizational Model

### 5.1 Country

- Country is the top-level administrative entity.
- Country has a unique code, a unique name, and lifecycle status values such as `ACTIVE` and `INACTIVE`.
- Only `TS_ADMIN_MASTER` can create, update, and delete Countries.
- One Country can own multiple Offices.

### 5.2 Office

- Office belongs to exactly one Country.
- Office lifecycle uses status values such as `ACTIVE` and `INACTIVE`.
- Office configuration is owned at Office level.
- Only `TS_ADMIN_MASTER` can create, update, and delete Offices.
- Office creation bootstraps:
  - the Office
  - the Office configuration
  - an initial Business Unit
  - an initial Office administrator employee

### 5.3 Business Unit

- Business Units belong to exactly one Office.
- Business Unit code uniqueness is enforced within the parent Office.
- `TS_ADMIN` scope is Business Unit based.
- Active `TS_ADMIN` employees in an Office are automatically kept in scope for all Business Units in that Office, including newly created Business Units.
- Business Units do not own operational configuration anymore.
- Business Unit detail shows inherited Office configuration as read-only.
- Business Units can be deleted only when no protected references remain.

### 5.4 Employees

- Employees belong to exactly one Office.
- Each employee has:
  - one primary Business Unit
  - one or more Business Units in scope
  - zero or more active roles
- The primary Business Unit must also be in Business Unit scope.
- An employee with an active `TS_ADMIN` role always keeps full Business Unit scope for their Office while that role remains active.
- Employee create/edit/delete is handled by `TS_ADMIN` inside the active Office and scoped Business Units.
- Cross-Office employee transfer is handled separately by `TS_ADMIN_MASTER`.
- The transfer workflow does not mutate the existing employee Office.
- Instead it:
  - archives the source employee email
  - deactivates the source employee record
  - closes the source employee's active internal roles and Business Unit scope
  - creates a new active employee record in the target Office
  - moves the real login email to the new target-Office employee record
- The source employee keeps the historical `employee_id`, source Office
  history, and source employee code.
- The target Office receives a new employee record with a new unique employee
  code and a new `employee_id`.
- Employee detail in System Management also shows a read-only grid of the
  employee's active project assignments, including valid cross-office project
  staffing where the employee's home Office / Business Unit differs from the
  target project's Office / Business Unit.
- Cross-office assignment visibility is informational for origin-office users:
  it must show the employee's full active project picture, but it does not
  grant permission to edit or inspect target-office project data beyond the
  safe row fields shown in the grid.
- Direct navigation to linked project detail screens is available only when
  the current user is authorized for the target project scope.

## 6. Office-Level Configuration

The Office configuration currently contains:
- Approval Mode
- Allow Employee Withdraw
- Timesheet Cutoff Date (stored for compatibility; UI-disabled)
- Count Non-billable In Daily Limit (stored for compatibility; UI-disabled)
- Archive After Years
- Enable Timer
- Enable Leave Integration
- Enable Copy Previous Week

Behavior:
- Business Units inherit these values at runtime from their parent Office.
- Business Unit admins can view inherited values but cannot edit them from the BU screen.
- `Approval Mode` is retained as an Office configuration field, but only
  `PROJECT` is currently implemented and user-selectable in the UI. Legacy
  `LINE` and `MIXED` reference values remain in the schema/reference data for
  compatibility and are hidden from Office configuration screens.
- `Timesheet Cutoff Date` is retained in the schema and still acts as a period
  lock when configured outside the Office HTML UI, but it is not user-editable
  in Office or Business Unit configuration screens.
- A `TS_ADMIN` may override the lock for a specific timesheet with audit.
- Daily limit validation always counts all charged time for the date, including
  billable and non-billable lines. The legacy `Count Non-billable In Daily
  Limit` field is retained in the schema but is not user-editable in the UI.
- `Enable Timer` and `Enable Leave Integration` are reserved compatibility
  switches and are not user-editable in Office or Business Unit configuration
  screens.
- `Enable Copy Previous Week` controls whether `My Timesheets` exposes a
  user-initiated `Copy Prev. Week` action.
- `Copy Prev. Week` creates the selected weekly timesheet and preloads it from
  the employee's most recent approved earlier timesheet.
- copied lines must still pass the normal charge-target, working-day, and
  daily-limit validations for the new week.
- `Enable Timer` and `Enable Leave Integration` remain inactive placeholders in
  the current implementation.

## 7. System Management Scope

### 7.1 Country-Scoped Masters

The following masters are managed by `TS_ADMIN_MASTER` above Office level:
- Countries
- Offices
- Employee Transfers

### 7.2 Office-Scoped Masters

The following masters are managed at Office level:
- Clients
- Cost Centers
- Pricing Models

### 7.3 Business-Unit-Scoped Masters

The following masters remain Business Unit scoped:
- Business Units
- Employees and Business Unit scope
- Internal Categories
- General Charge Codes
- Projects
- Project Assignments
- Cross-Office Staffing
- Calendar Period Rules

## 8. System Management Features

### 8.1 Countries

- `TS_ADMIN_MASTER` can create, edit, and guarded-delete Countries.
- Country detail shows:
  - general Country data
  - related Office count
- Country deletion is blocked when dependent Offices still exist.

### 8.2 Offices

- `TS_ADMIN_MASTER` can create, edit, and guarded-delete Offices.
- Office create/edit requires selecting an existing Country.
- Office collection shows:
  - Office status filters in the page header
  - active employee count per Office
  - a bottom `Create Office` action that opens a standalone create screen
- Office detail shows:
  - parent Country
  - general Office data
  - editable Office configuration
  - read-only Office administrators
- Office collection does not embed an inline create form.
- Office detail uses a full-width edit layout without the legacy `Current State` summary panel.
- Office deletion is blocked when dependent records still exist.
- Office deletion may remove setup-only bootstrap records in the same
  transaction when the Office has only its initial Business Unit, its initial
  Office administrator employee, Office configuration, and audit-only
  references. This avoids a self-delete deadlock for newly-created Offices
  while still blocking Offices with operational dependencies.

### 8.2A Employee Transfers

- `TS_ADMIN_MASTER` can open a dedicated `Employee Transfer` screen from System
  Management.
- The transfer screen is master-only and is separate from ordinary employee
  administration.
- The workflow is source-selection first, then target setup.
- Source employee transfer is blocked until live operational dependencies are
  cleared.
- The current implementation blocks transfer when the source employee still has:
  - open timesheets
  - active direct reports
  - active owned projects
  - active managed projects
  - active project assignments
  - active cross-office staffing assignments
  - active General Charge Code approval-role memberships
  - pending approval items
- On success, the workflow:
  - archives the source employee email
  - sets the source employee status to `INACTIVE`
  - closes active source role assignments
  - closes active source Business Unit scope assignments
  - creates the new target-Office employee record
  - applies the selected target Business Unit scope and target role set
  - writes a dedicated transfer audit event

### 8.2 Clients

- Clients are Office-level only.
- Client create/edit does not require a Business Unit.
- Parent Client relationships must remain inside the same Office.
- Client Management collection now expands each client into one row per Business
  Unit that currently owns active projects for that client.
- Each client row shows:
  - the Business Unit name
  - the number of active projects for that client and Business Unit
  - the number of distinct active employees with active assignments to those
    active projects
- Project-count navigation is guarded by the clicked row Business Unit.
- If the caller is not assigned to that Business Unit, the system shows an
  access error instead of redirecting to Project Management.
- Client deletion is guarded by referential integrity.

### 8.3 Cost Centers

- Cost Centers are Office-level only.
- Cost Center create/edit does not require a Business Unit.
- Cost Center deletion is guarded by referential integrity.

### 8.4 Pricing Models

- Pricing Models are Office-level only.
- A Pricing Model contains:
  - name
  - description
- Pricing Model deletion is guarded by referential integrity.

### 8.5 Internal Categories

- Internal Categories remain Business Unit scoped.
- Internal Category deletion is guarded by referential integrity.

### 8.6 General Charge Codes

- General Charge Codes remain Business Unit scoped.
- Each General Charge Code must be linked to one Cost Center from the same active Office.
- The `Common Code` attribute is no longer part of the model.
- They keep lifecycle, approval, billing, and validity-window behavior.
- When `Requires Approval` is enabled, the General Charge Code must keep at least one
  configured approver role.
- Approver roles can be:
  - existing internal TS roles
  - office-scoped ad-hoc General Charge Code approval roles
- Selected ad-hoc General Charge Code approval roles must be active and must keep at
  least one active member employee.
- Ad-hoc General Charge Code approval roles are managed in System Management together
  with employee membership assignment, dependency visibility, and routing-coverage
  warnings.
- Referenced ad-hoc General Charge Code approval roles cannot be set inactive and
  cannot be left without active member employees.
- General Charge Code deletion is guarded by referential integrity.

### 8.7 Calendars And Special Days

- Yearly Calendars are managed in System Management.
- Yearly Calendars are Office-level and shared by all Business Units in the Office.
- A Yearly Calendar can stay active even when the current date is outside the calendar year.
- Only one Yearly Calendar can exist for a given year in an Office.
- Employees should resolve an assigned Office calendar before time entry. When an
  active employee in an active Office has no assigned calendar, employee
  create/transfer/scope-management flows and compatibility backfill assign the
  preferred active Office calendar automatically when one is available.
- When an employee has an assigned Office calendar but their current primary
  Business Unit has no matching Office-calendar period rules yet, the system may
  clone the Office's single existing Business Unit rule pattern into the
  employee's primary Business Unit to keep timesheet validation operable.
- Calendar detail shows:
  - year summary totals
  - month view
  - special-day list
- Calendar Special Days are created, edited, and deleted inside the selected Yearly Calendar.
- Supported Special Day types are:
  - `NATIONAL_HOLIDAY`
  - `LOCAL_HOLIDAY`
  - `TIMIA_DAY`
  - `OTHER`
- The system enforces:
  - a Special Day date must belong to the selected calendar year
  - one Special Day per date inside a Yearly Calendar

### 8.8 Projects

- Projects remain Business Unit scoped.
- `TS_ADMIN` can create, edit, and guarded-delete projects within active Office
  and Business Unit scope.
- `PROJECT_OWNER` can create projects and can edit or guarded-delete only the
  projects they own within active Office and Business Unit scope.
- Project deletion is guarded by referential integrity.
- The following fields are mandatory for project setup:
  - Business Unit
  - Project Code
  - Project Name
  - Project Owner
  - Project Manager
  - Client
  - Internal Category
  - Cost Center
  - Pricing Model
  - Start Date
- Validation rules:
  - project owner must hold `PROJECT_OWNER`
  - project manager must hold `PROJECT_MANAGER`
  - projects created by a `PROJECT_OWNER` are always owned by the current
    employee profile regardless of submitted payload
  - client must belong to the same Office
  - cost center must belong to the same Office
  - pricing model must belong to the same Office
  - internal category must belong to the same Business Unit
  - `end_date >= start_date`
  - `close_date >= start_date`
- Project Management collection shows:
  - Business Unit name instead of code
  - Client name
  - project owner full name
  - project manager full name
  - total distinct assigned employees, including inactive assignments
- The collection also supports an inline Client filter that preserves the
  selected Project Status.
- Employee-count drill-down opens Project Assignment Management prefiltered to
  the selected project.

### 8.9 Project Assignments

- Project Assignments remain Business Unit scoped through the Project.
- Project Assignments are the normal same-office staffing model.
- `TS_ADMIN` can create, edit, and guarded-delete assignments in scoped
  projects.
- `PROJECT_OWNER` can create, edit, and guarded-delete assignments only for
  projects they own within active Office and Business Unit scope.
- `PROJECT_MANAGER` can create, edit, and guarded-delete assignments only for
  projects they manage within active Office and Business Unit scope.
- Assignment creation is blocked for closed projects.
- The assigned employee must be active and in the project Business Unit scope.
- Assignment dates must stay inside the allowed project date window.
- Project Assignment deletion is guarded by referential integrity.
- Project Assignment Management collection now shows Client and Project Name
  columns and supports a dependent Client -> Project filter pair.

### 8.9A Cross-Office Staffing

- Cross-Office Staffing is a dedicated staffing model separate from normal
  Project Assignments.
- Cross-Office Staffing is used only when the employee Office differs from the
  target project Office.
- Same-office staffing remains on normal Project Assignments and must not be
  created through the Cross-Office Staffing flow.
- Cross-Office Staffing does not move the employee into the target Office and
  does not change the employee's home Office or home Business Unit context.
- `TS_ADMIN` can create, edit, and guarded-delete cross-office staffing in
  scoped target projects.
- `PROJECT_OWNER` can create, edit, and guarded-delete cross-office staffing
  only for projects they own.
- `PROJECT_MANAGER` can create, edit, and guarded-delete cross-office staffing
  only for projects they manage.
- Cross-office staffing authority follows the target project scope, not the
  employee origin Office.
- Cross-office staffing creation is blocked for closed projects.
- The assigned employee must be active.
- The staffing window must stay inside the allowed project date window.
- The system blocks overlapping active staffing windows for the same
  employee/project combination across normal Project Assignments and
  Cross-Office Staffing.
- Normal Project Assignment and Cross-Office Staffing writes use the same
  active-window overlap rule; an inactive staffing record does not block a new
  active window.
- Cross-Office Staffing stores origin-office context for audit and reporting
  interpretation.
- Cross-Office Staffing is managed in its own dedicated System Management UI
  and does not replace normal Project Assignment Management.
- On the create screen, selecting Origin Office narrows the eligible employee
  list to that office, and target Project selection fills the read-only target
  Office and target Business Unit context.

### 8.10 Calendar Period Rules

- Calendar Period Rules are managed in System Management.
- Yearly Calendars remain Office-level, but each Calendar Period Rule belongs to one Business Unit inside that Office calendar.
- The system enforces:
  - `effective_to >= effective_from`
  - no overlapping rules within the same Business Unit and Yearly Calendar
  - overlapping rules are allowed across different Business Units in the same Office calendar
- Calendar Period Rules can optionally mark Saturdays, Sundays, or both as normal working days for that Business Unit period.
- When weekend work is enabled, Saturday and Sunday max-hours are configured explicitly on the same Calendar Period Rule.
- Active Special Days still override a weekend working flag and keep the overlapping date non-working.
- Calendar Period Rules can be deleted only when no protected references depend on them.

### 8.11 Guarded Deletes

Guarded delete actions exist in the UI for selected administrative records:
- Office
- Business Unit
- Employee
- Yearly Calendar
- Calendar Special Day
- Client
- Internal Category
- Cost Center
- Pricing Model
- Calendar Period Rule
- General Charge Code
- Project
- Project Assignment
- Cross-Office Staffing

Delete behavior:
- proceed only when protected dependencies do not exist
- do not cascade-delete business data
- show an error when referential integrity blocks the deletion

### 8.12 Current System Management UI Pattern

- Standard create and edit screens use the same standalone layout direction.
- Detail screens remove non-essential current-state summary boxes when the data is already represented by editable fields.
- Delete actions remain on detail screens and are placed as separate bottom actions.
- Collection rows open detail screens through the primary item link in the first visible column.

## 9. TS Management

### 9.1 My Timesheets

- Employees manage their own weekly Monday-starting timesheets.
- The personal weekly list combines current and historical timesheets in one screen.
- The personal weekly list also shows missing Monday-starting weeks since
  employee record creation.
- Missing weeks are computed from the first Monday on or after employee record creation through the current Monday.
- Selecting a missing week preloads the create controls for that week instead of auto-creating a timesheet.
- One employee can have at most one weekly timesheet per week.
- When Office configuration enables it, employees can use `Copy Prev. Week` to
  create the selected week from the most recent approved earlier timesheet.
- Timesheet lines charge either:
  - a Project
  - a General Charge Code
- A project line is allowed only when the employee has active staffing for the
  work date through either:
  - a normal Project Assignment
  - a Cross-Office Staffing record
- Weekend entry is blocked by default.
- Saturday and Sunday become chargeable only when the active Business Unit Calendar Period Rule marks them as working and no active Special Day overrides them.
- Calendar Special Days, weekend-working behavior, daily limits, and valid
  General Charge Codes continue to come from the employee's home-office
  timesheet context.
- If the employee's home-office calendar marks a date as holiday or other
  non-working Special Day, the employee cannot charge that date to another
  Office's project.
- If the target project Office marks a date as holiday but the employee's
  home-office calendar treats the date as working, the target-office holiday
  does not block charging by itself.
- The timesheet detail UI shows submission and approval metadata using short
  dates while preserving the full stored timestamps in the data model.
- Draft timesheets are deletable only while they remain pure drafts with no
  submission-cycle history. A timesheet that was submitted and later withdrawn
  may return to `CREATED`, but it remains non-deletable because submission
  history must be preserved for auditability.

### 9.2 History

- Historical weekly records are accessed from the shared personal timesheet list.
- The legacy history route redirects to the merged personal timesheet screen.

### 9.3 Project Management UI

- Available to `TS_ADMIN`, `PROJECT_OWNER`, and `PROJECT_MANAGER`.
- Shows role-scoped projects with status filters:
  - `All`
  - `Active`
  - `Closed`
  - `Draft`
- Supports an inline `Client` filter that preserves the current selected
  status.
- Summary grid shows:
  - project name
  - client
  - project status
  - approved hours
  - pending submitted timesheets
  - missing timesheets
- project staffing-derived counts and missing-timesheet summaries use both
  normal Project Assignments and Cross-Office Staffing
- Drill-down behavior:
  - `TS_ADMIN` can open the System Management project detail screen from the
    project name
  - `PROJECT_OWNER` can open the editable System Management project detail
    screen for owned projects from the project name
  - `PROJECT_MANAGER` does not get the project-name detail link
  - approved hours open the project-time report preloaded to the project
- nonzero pending timesheets open the Approval Worklist prefiltered to the
  selected project
- missing timesheets open the project missing-timesheets report preloaded to
  the project

### 9.4 Project Time Inquiry

- Available to `PROJECT_OWNER` and `PROJECT_MANAGER`.
- Shows live project-charged time in the caller’s owned or managed project scope.

## 10. Approvals

- The approval worklist supports:
  - project approval items assigned to one Project Manager
  - General Charge Code approval items routed to one or more eligible roles
- `TS_ADMIN` can open the same `/approvals/` workspace in an oversight mode for
  approval items that belong to Business Units inside the active Office and
  scoped Business Units.
- Project-office approval authority covers project time charged by
  cross-office staffed employees the same way it covers same-office assigned
  employees.
- The `TS_ADMIN` oversight view adds:
  - pending-age and stalled visibility
  - filters by Business Unit, employee, project, target type, and aging
  - the same `Approval Worklist` title used by the approver-facing workspace
  - pending grid rows show employee name, target, Business Unit, approver
    name, TS submission date, pending age, and queue state
  - read-only approval detail access
  - links to the related timesheet and project for follow-up
  - a compact single-section approval context with employee name, target, BU
    name, approver name, and TS submission date shown in the top row
- A General Charge Code approval item is actionable by any active employee who matches
  one of the snapped approver roles for that item.
- The first approval or rejection decision closes the General Charge Code approval item.
- Project Managers can still view and act on project approval items assigned to them.
- Project Owners can review approval items for owned projects but do not get
  approval authority from ownership alone.
- `TS_ADMIN` oversight does not grant approve/reject authority unless the same
  employee independently matches the routed approver assignment or General
  Charge Code approval role.
- In the approved Phase 3 scope, `TS_ADMIN` oversight follows:
  - target-project Office and scoped target Business Units for project approval
    items
  - weekly-timesheet home Business Unit scope for General Charge Code approval
    items
- `TS_ADMIN` uses related-timesheet exception actions for operational cleanup:
  reopen approved timesheets, withdraw approved timesheets back to submitted,
  archive approved timesheets, and restore archived timesheets.

## 11. Reports

Implemented reports:
- Project Time
- Pending Approvals
- Missing Timesheets by Project
- Archived Timesheets
- Audit History
- Integration Jobs
- Employee Utilization
- Office / BU Time Summary
- General Charge Code Usage
- Approval Turnaround

Audience highlights:
- `USER`: personal history stays in `My Timesheets`
- `PROJECT_OWNER`: Project Time, Missing Timesheets by Project
- `PROJECT_MANAGER`: Project Time, Pending Approvals, Missing Timesheets by Project
- `TS_ADMIN`: administrative reports across scoped Business Units, including:
  - Missing Timesheets by Project
  - Archived Timesheets
  - Audit History
  - Integration Jobs
  - Employee Utilization
  - Office / BU Time Summary
  - General Charge Code Usage
  - Approval Turnaround

Cross-office staffing reporting rules:
- Project Time includes charged project time from employees staffed from other
  Offices when the employee is validly staffed to the target project.
- Project Time uses one grouped HTML results grid with:
  - one summary row per visible weekly-timesheet `BU` / `Project`
  - nested week summary rows under each visible `BU` / `Project`
  - expand/collapse visibility at both the project and week levels
  - flat CSV export rows that keep the same filtered detail scope
- For `TS_ADMIN`, the Project Time Business Unit filter is scoped and applied
  to the charged target project's Business Unit. The displayed `BU` column
  remains the weekly-timesheet home Business Unit for compatibility.
- Missing Timesheets by Project derives staffing windows from both normal
  Project Assignments and Cross-Office Staffing.
- Office / BU summary-style reports still remain based on the weekly-timesheet
  home Business Unit rather than target-project Office attribution unless a
  later reporting change says otherwise.

Pending approval reporting rules:
- Pending Approvals shows week start date as the first column.
- Pending Approvals no longer shows the internal approval-item identifier or a
  separate status column in the report grid/export.

CSV export behavior:
- The report viewer supports CSV export for:
  - Project Time
  - Pending Approvals
  - Missing Timesheets by Project
  - Archived Timesheets
  - Audit History
  - Integration Jobs
  - Employee Utilization
  - Office / BU Time Summary
  - General Charge Code Usage
  - Approval Turnaround
- CSV export always uses the currently applied filters and the same server-side
  scope rules as the visible report grid.
- Missing Timesheets by Project keeps its dedicated API export flow in addition
  to the HTML/UI export path.

Advanced admin-report behavior:
- Employee Utilization:
  - compares expected chargeable capacity against worked hours by employee
  - expected capacity is derived from the employee calendar, active Calendar
    Period Rules, weekend-working rules, and active Special Days
  - supports filtering by Business Unit, employee, and work-date range
- Office / BU Time Summary:
  - aggregates project-charged total, billable, and non-billable hours by
    Office, Business Unit, and Project
  - excludes General Charge Code lines from the summary rows
  - includes cross-office project time from either perspective:
    - origin-office / weekly-timesheet home BU when that home BU is in scope
    - target-project Office / BU when that project BU is in scope and the
      employee belongs to another Office
  - treats the Business Unit filter as a scoped reporting-perspective filter:
    a selected in-scope Business Unit must include project-charged rows when
    either the weekly timesheet home Business Unit or the charged target
    project Business Unit matches it
  - ignores or rejects out-of-scope Business Unit filter values for
    authorization purposes; a tampered filter must never widen report scope
  - displays the charged project's Office and Business Unit values on the
    returned project rows
  - supports filtering by Business Unit and work-date range
- General Charge Code Usage:
  - aggregates internal charging usage by General Charge Code
  - supports filtering by Business Unit, General Charge Code, employee, and
    work-date range
- Approval Turnaround:
  - shows pending and completed approval items with elapsed hours and aging
    buckets
  - identifies stalled pending items
  - supports filtering by Business Unit, project, approver, status, and
    submitted-date range

Missing Timesheets by Project behavior:
- filters by one or more accessible projects
- `PROJECT_OWNER` sees owned projects
- `PROJECT_MANAGER` sees managed projects
- users with both roles see the union of owned and managed projects
- `TS_ADMIN` sees projects in current Office and Business Unit scope
- report rows show:
  - project name
  - employee name
  - employee email
  - missing week start date
- missing weeks are derived from active project staffing windows from both
  normal Project Assignments and Cross-Office Staffing plus missing weekly
  timesheets
- CSV export is available in the UI and through the API

## 12. Audit Expectations

Audit coverage is required for sensitive state changes, including:
- employee identity and role changes
- Business Unit scope changes
- project ownership and management changes
- project staffing changes, including Cross-Office Staffing
- timesheet line replacement, as a summary event rather than per-line audit rows
- timesheet submit, withdraw, reopen, archive, restore
- approval approve and reject
- guarded administrative deletes
- project missing-timesheet report generation and export
- report CSV export for the other supported report slices
Audit events may carry a `correlation_id` when a caller supplies one, allowing
related events from the same workflow/request to be connected without changing
row-level authorization or report scoping.

## 13. Out Of Scope For v8.0

- pricing calculations beyond storing a project Pricing Model
- JSON API parity for UI-only workflows such as Employee Transfer and
  Cross-Office Staffing
- cascade deletes for administrative masters
- target-project-Office `TS_ADMIN` approval oversight expansion beyond the
  current home-Business-Unit admin visibility model
- retagging Office / BU summary analytics from weekly-timesheet home Business
  Unit attribution to target-project Office attribution
- a JSON or public API surface for Cross-Office Staffing unless separately
  approved
- production custom domain, production HA sizing, production data migration,
  and browserless API-client authentication are outside Milestone 1
