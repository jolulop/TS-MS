# Functional Specification v5.8

## 1. Purpose

Define the current implemented behavior of the Timesheet Management System after the Office refactor, the expanded System Management feature set, and the latest UI consolidation updates.

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
- `Project Management`, `Reports`, `Approval Worklist`, and `Project Time Inquiry`
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

## 6. Office-Level Configuration

The Office configuration currently contains:
- Approval Mode
- Allow Employee Withdraw
- Timesheet Cutoff Date
- Count Non-billable In Daily Limit
- Archive After Years
- Enable Timer
- Enable Leave Integration
- Enable Copy Previous Week

Behavior:
- Business Units inherit these values at runtime from their parent Office.
- Business Unit admins can view inherited values but cannot edit them from the BU screen.
- `Timesheet Cutoff Date` acts as a period lock for normal employee edit/submit behavior on older timesheets.
- A `TS_ADMIN` may override the lock for a specific timesheet with audit.
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

### 8.2 Clients

- Clients are Office-level only.
- Client create/edit does not require a Business Unit.
- Parent Client relationships must remain inside the same Office.
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
- Ad-hoc General Charge Code approval roles are managed in System Management together
  with employee membership assignment.
- General Charge Code deletion is guarded by referential integrity.

### 8.7 Calendars And Special Days

- Yearly Calendars are managed in System Management.
- Yearly Calendars are Office-level and shared by all Business Units in the Office.
- A Yearly Calendar can stay active even when the current date is outside the calendar year.
- Only one Yearly Calendar can exist for a given year in an Office.
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

### 8.9 Project Assignments

- Project Assignments remain Business Unit scoped through the Project.
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
- Weekend entry is blocked by default.
- Saturday and Sunday become chargeable only when the active Business Unit Calendar Period Rule marks them as working and no active Special Day overrides them.
- The timesheet detail UI shows submission and approval metadata using short
  dates while preserving the full stored timestamps in the data model.

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
- Summary grid shows:
  - project name
  - project status
  - approved hours
  - pending submitted timesheets
  - missing timesheets
- Drill-down behavior:
  - `TS_ADMIN` can open the System Management project detail screen from the
    project name
  - `PROJECT_OWNER` can open the editable System Management project detail
    screen for owned projects from the project name
  - `PROJECT_MANAGER` does not get the project-name detail link
  - approved hours open the project-time report preloaded to the project
  - pending timesheets open the approval worklist for owned projects only
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
- The `TS_ADMIN` oversight view adds:
  - pending-age and stalled visibility
  - filters by Business Unit, employee, project, target type, and aging
  - read-only approval detail access
  - links to the related timesheet and project for follow-up
- A General Charge Code approval item is actionable by any active employee who matches
  one of the snapped approver roles for that item.
- The first approval or rejection decision closes the General Charge Code approval item.
- Project Managers can still view and act on project approval items assigned to them.
- Project Owners can review approval items for owned projects but do not get
  approval authority from ownership alone.
- `TS_ADMIN` oversight does not grant approve/reject authority unless the same
  employee independently matches the routed approver assignment or General
  Charge Code approval role.
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
  - aggregates total, billable, and non-billable hours by Office and Business
    Unit
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
- missing weeks are derived from active project assignments and missing weekly timesheets
- CSV export is available in the UI and through the API

## 12. Audit Expectations

Audit coverage is required for sensitive state changes, including:
- employee identity and role changes
- Business Unit scope changes
- project ownership and management changes
- timesheet submit, withdraw, reopen, archive, restore
- approval approve and reject
- guarded administrative deletes
- project missing-timesheet report generation and export
- report CSV export for the other supported report slices

## 13. Out Of Scope For v5.8

- pricing calculations beyond storing a project Pricing Model
- Office-level JSON admin API
- cascade deletes for administrative masters
