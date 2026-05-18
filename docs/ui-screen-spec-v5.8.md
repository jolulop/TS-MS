# UI Screen Specification v5.8

## 1. Purpose

Describe the current server-rendered UI screens and behaviors implemented in the repository.

## 2. Navigation

Authenticated left-panel sections:
- `My info`
- `TS/Project Management`
- `System Management`

Role-aware visibility applies to sections, menus, and actions.

`My info` contains:
- `Profile`
- `Dashboard` except for basic `USER`-only sessions
- `My Timesheets`
- dashboard summary cards use a bold white-card title line with inline `-> count`
  formatting

`TS/Project Management` contains:
- `Project Management` when authorized
- `Reports`
- `Approval Worklist` when authorized
- `Project Time Inquiry` when authorized
- the whole section is hidden for basic `USER`-only sessions

## 3. System Management Navigation

### 3.1 `TS_ADMIN_MASTER`

Visible section:
- Countries
- Offices

### 3.2 `TS_ADMIN`

Visible sections:
- Business Units
- Employees
- Calendars
- Clients
- Internal Categories
- Cost Centers
- Pricing Models
- General Charge Codes
- Projects
- Project Assignments
- Calendar Period Rules

### 3.3 `PROJECT_OWNER`

Visible sections:
- Projects
- Project Assignments

### 3.4 `PROJECT_MANAGER`

Visible sections:
- Project Assignments

## 4. Shared Collection Behavior

- Collections use a shared administrative shell.
- Collection rows open detail through the first visible item link.
- Some legacy action markup may remain hidden in shared table templates for future extensibility.
- Status-managed collections expose a status filter bar where applicable.
- Create forms live on collection screens.
- Update and delete actions live on detail screens.

## 4A. Shared Detail Layout Behavior

- Standard create and edit screens follow the same standalone layout direction where implemented.
- Detail screens remove redundant current-state summary panels when they do not add new information.
- Delete actions remain available on detail screens as separate bottom actions.

## 5. Country And Office Screens

### SCR-098 Country Management

- Access: `TS_ADMIN_MASTER`
- Collection:
  - list Countries
  - filter by status
  - create Country
- Detail:
  - edit Country code, name, and status
  - show read-only Office count
  - guarded delete action

### SCR-100 Office Management

- Access: `TS_ADMIN_MASTER`
- Collection:
  - list Offices
  - show Office status filters to the right of the main page title
  - show `Country`, `Office`, `Employees`, and `Status`
  - remove the `Current Records` heading above the grid
  - remove inline Office creation from the collection screen
  - provide a bottom `Create Office` button that opens a standalone setup screen
- Standalone create:
  - require Country selection
  - capture Office configuration
  - capture bootstrap Business Unit data
  - capture bootstrap admin user data
- Detail:
  - edit parent Country
  - edit general Office data
  - edit Office configuration
  - show read-only Office administrators
  - remove the legacy `Current State` summary panel
  - render Office edit fields in a wider full-width layout
  - guarded delete action

## 6. Business Unit Screens

### SCR-105 Business Unit Management

- Access: `TS_ADMIN`
- Collection:
  - create Business Unit in active Office
- Detail:
  - edit Business Unit identity and status
  - show inherited Office configuration as read-only
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

## 7. Employee Screens

### SCR-110 Employee Management

- Access: `TS_ADMIN`
- Collection:
  - status filter
  - create employee
  - assign primary Business Unit
  - assign Business Unit scope
  - assign roles
- Detail:
  - edit core employee data
  - edit roles
  - edit Business Unit scope
  - guarded delete action

Important UI behavior:
- new employee creation does not preselect the current admin’s Business Unit in scope
- selected primary Business Unit is included automatically in the employee scope
- employee detail removes the current-state panel
- employee detail places core data in one row and moves delete to the bottom

## 8. Classification And Master Screens

### SCR-130 Client Management

- Access: `TS_ADMIN`
- Scope: Office
- Collection:
  - status filter
  - create client
- Detail:
  - edit code, name, parent client, status
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-140 Internal Category Management

- Access: `TS_ADMIN`
- Scope: Business Unit
- Collection:
  - status filter
  - create internal category
- Detail:
  - edit category fields
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-150 Cost Center Management

- Access: `TS_ADMIN`
- Scope: Office
- Collection:
  - status filter
  - create cost center
- Detail:
  - edit cost center fields
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-155 Pricing Model Management

- Access: `TS_ADMIN`
- Scope: Office
- Collection:
  - create pricing model
- Detail:
  - edit name and description
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-170 General Charge Code Management

- Access: `TS_ADMIN`
- Scope: Business Unit
- Collection:
  - status filter
  - create general charge code
  - mandatory Cost Center dropdown populated from the active Office
  - approver-role multiselect combining:
    - existing internal TS roles
    - office ad-hoc General Charge Code approval roles
- Detail:
  - edit Cost Center assignment, approver roles, lifecycle, validity, and behavior flags
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-169 General Charge Code Approval Role Management

- Access: `TS_ADMIN`
- Scope: active Office
- Collection:
  - status filter
  - create ad-hoc General Charge Code approval role
  - assign member employees from the active Office
- Detail:
  - edit role code, name, description, members, and status
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-115 Calendar Management

- Access: `TS_ADMIN`
- Scope: active Office
- Collection:
  - status filter
  - create yearly calendar
- Detail:
  - edit yearly calendar year, name, and status
  - show year summary
  - show month navigation and month view
  - show special-day list
  - create special day from the calendar detail
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-117 Special Day Creation

- Access: `TS_ADMIN`
- Scope: selected Yearly Calendar
- Create:
  - select special day date
  - select special day type
  - save inside the selected Yearly Calendar

### SCR-118 Special Day Detail

- Access: `TS_ADMIN`
- Scope: selected Yearly Calendar
- Detail:
  - edit special day date and type
  - guarded delete action

## 9. Project Screens

### SCR-180 Project Management

- Access: `TS_ADMIN` or `PROJECT_OWNER`
- Scope:
  - `TS_ADMIN`: scoped Business Units in active Office
  - `PROJECT_OWNER`: owned projects inside active Office and scoped Business Units
- Collection:
  - status filter with `All`, `Draft`, `Active`, `Closed`
  - create project
- Mandatory create/edit fields:
  - Business Unit
  - Project Code
  - Project Name
  - Description
  - Project Owner
  - Project Manager
  - Client
  - Internal Category
  - Cost Center
  - Pricing Model
  - Start Date
  - End Date
  - Close Date
  - Billable
  - Status
- Detail:
  - edit project data from the detail page
  - guarded delete action
  - `PROJECT_OWNER` sees only their own projects and the `Project Owner` field
    stays fixed to the current employee profile
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-190 Project Assignment Management

- Access: `TS_ADMIN`, `PROJECT_OWNER`, or `PROJECT_MANAGER`
- Scope:
  - `TS_ADMIN`: scoped Project Business Units in active Office
  - `PROJECT_OWNER`: assignments for owned projects inside active Office and
    scoped Business Units
  - `PROJECT_MANAGER`: assignments for managed projects inside active Office and
    scoped Business Units
- Collection:
  - status filter
  - create project assignment
- Detail:
  - edit assignment dates and status
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-120 Calendar Period Rule Management

- Access: `TS_ADMIN`
- Scope: active Office
- Collection:
  - status filter
  - Business Unit selector
  - create period rule
  - Working On Saturdays checkbox
  - Saturday Max Hours input
  - Working On Sundays checkbox
  - Sunday Max Hours input
- Detail:
  - Business Unit selector
  - edit date range and daily hour limits
  - Working On Saturdays checkbox
  - Saturday Max Hours input
  - Working On Sundays checkbox
  - Sunday Max Hours input
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

## 10. TS Management Screens

### SCR-200 My Timesheets

- Access: authenticated `USER`
- features:
  - merged personal weekly list for current and historical timesheets
  - includes synthetic missing-week rows for Monday-starting weeks with no
    created timesheet since employee record creation
  - single-row filter panel with:
    - `Status`
    - `Week Start From`
    - `Week Start To`
  - header-level `Week Start Date` selector and `Create Timesheet` action
  - when Office configuration enables it, a `Copy Prev. Week` action beside
    create
  - create flow opens the weekly editor directly for the selected date
  - `Copy Prev. Week` creates the selected week and preloads lines from the
    employee's most recent approved earlier timesheet
  - open weekly timesheets into the dedicated edit/detail screen
  - list columns:
    - `Week Start`
    - `Week End`
    - `Status`
    - `Submitted At`
    - `Approved At`
  - list dates are shown using short-date formatting
  - clicking a missing week preloads the create controls with that week start
  - submit
  - withdraw if allowed
  - delete draft timesheets only when deletion is allowed by backend rules
  - timesheet detail shows `Submitted At` and `Approved At` using short-date
    formatting

### SCR-210 My History

- Access: authenticated `USER`
- features:
  - compatibility route only
  - redirects to `SCR-200 My Timesheets`

### SCR-211 Project Management

- Access: `TS_ADMIN`, `PROJECT_OWNER`, `PROJECT_MANAGER`
- features:
  - status filters:
    - `All`
    - `Active`
    - `Closed`
    - `Draft`
  - summary grid columns:
    - `Name`
    - `Status`
    - `Appr. Hours`
    - `Pend. Appr.`
    - `Missing TS`
  - project name opens:
    - editable System Management project detail for `TS_ADMIN`
    - editable owned-project System Management detail for `PROJECT_OWNER`
    - no link for `PROJECT_MANAGER`
  - approved-hours value opens the project-time report preloaded to that project
  - pending-timesheet value opens the approval worklist for owned projects only
  - missing-timesheet value opens the missing-timesheets report preloaded to that project

### SCR-220 Project Time Inquiry

- Access: `PROJECT_OWNER` or `PROJECT_MANAGER`
- features:
  - scoped live inquiry
  - project-related filters
  - totals

## 11. Approval Screens

### SCR-300 Approval Worklist

- Access:
  - `TS_ADMIN` for scoped oversight visibility
  - `PROJECT_MANAGER`
  - `PROJECT_OWNER` owned-project visibility
  - matching General Charge Code approver scope
- features:
  - shared `/approvals/` route with role-specific behavior
  - `TS_ADMIN` oversight variant:
    - filter panel with search, Business Unit, employee, project, target type,
      and aging
    - desktop filter layout uses three fields per row across two rows
    - pending approval grid with approver and stalled-age visibility
    - recent outcomes section
    - read-only approval detail
    - links to related timesheet and related project
  - approver variant:
    - pending approval list
    - no top summary count tiles
    - completed decision history section labeled `Last actions`
    - approval detail
    - approve when the current user is an actual approver for the item
    - reject when the current user is an actual approver for the item

### SCR-201 Weekly Timesheet Detail

- Access: authenticated `USER` for own timesheets, `TS_ADMIN` for scoped admin
  review
- features:
  - normal employee edit and submit/withdraw behavior stays unchanged
  - `TS_ADMIN` read-only visibility for scoped timesheets outside self-service
  - `TS_ADMIN` exception actions when authorized by status and scope:
    - reopen approved timesheets
    - withdraw approved timesheets back to `SUBMITTED`
    - archive approved timesheets
    - restore archived timesheets
  - each exception action requires the same backend authorization and audit
    behavior as the existing admin endpoints

## 12. Report Screens

### SCR-400 Reports Hub

- Access: role-based by report
- cards show:
  - clickable bold title with `->` and the scoped count shown beside it
  - summary
  - audience
- includes `Missing Timesheets by Project` for `PROJECT_OWNER`, `PROJECT_MANAGER`, and `TS_ADMIN`

### SCR-410 Report Viewer

- Access: enforced per report
- supports report-specific filters and scoped result grids
- when the report is exportable, shows an `Export CSV` action beside the normal
  report actions
- CSV export downloads the currently filtered scoped rows as a browser
  attachment

### SCR-420 Missing Timesheets By Project Report

- Access: `PROJECT_OWNER`, `PROJECT_MANAGER`, `TS_ADMIN`
- filter panel:
  - multi-select `Projects`
  - `PROJECT_OWNER` options are owned projects
  - `PROJECT_MANAGER` options are managed projects
  - combined owner/manager roles see the union of both
  - `TS_ADMIN` options come from current Office and Business Unit project scope
  - `Export CSV` button next to report actions
- result grid columns:
  - `Project Name`
  - `Employee Name`
  - `Employee Email`
  - `Missing TS Week Start`
- behavior:
  - empty project selection means all accessible projects
  - explicit out-of-scope selections do not widen the report scope
  - CSV export is downloaded as an attachment from the browser

### SCR-421 Exportable Existing Reports

- Project Time:
  - `Export CSV` available from the shared report viewer actions
- Pending Approvals:
  - `Export CSV` available from the shared report viewer actions
- Archived Timesheets:
  - `Export CSV` available from the shared report viewer actions
- Audit History:
  - `Export CSV` available from the shared report viewer actions
- Integration Jobs:
  - `Export CSV` available from the shared report viewer actions

## 13. Detail Screen Delete Pattern

Where delete exists:
- the delete action is on the detail page
- the action is separate from edit
- the action does not cascade
- blocked deletes return an inline error on the same screen
