# UI Screen Specification v6.1

## 1. Purpose

Describe the approved v6.1 server-rendered UI screens and behaviors for the
repository baseline.

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
- `Approval Worklist` when authorized
- `Reports`
- `Project Time Inquiry` when authorized
- the whole section is hidden for basic `USER`-only sessions

## 3. System Management Navigation

### 3.1 `TS_ADMIN_MASTER`

Visible section:
- Countries
- Offices
- Employee Transfers

### 3.2 `TS_ADMIN`

Visible sections:
- Employees
- Clients
- Projects
- Project Assignments
- Cross-Office Staffing
- Internal Categories
- Cost Centers
- Pricing Models
- Business Units
- Calendars
- Calendar Period Rules
- GCC Approval Roles
- General Charge Codes

### 3.3 `PROJECT_OWNER`

Visible sections:
- Projects
- Project Assignments
- Cross-Office Staffing

### 3.4 `PROJECT_MANAGER`

Visible sections:
- Project Assignments
- Cross-Office Staffing

## 4. Shared Collection Behavior

- Collections use a shared administrative shell.
- Collection rows open detail through the first visible item link.
- Some legacy action markup may remain hidden in shared table templates for future extensibility.
- Status-managed collections expose a status filter bar where applicable.
- Standard CRUD collections use standalone create screens reached from the collection page.
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
  - provide a `Create Country` action that opens a standalone create screen
- Standalone create:
  - create Country code, name, and status
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
  - show a read-only active Project Assignments grid for the employee,
    including read-only cross-office project rows when relevant
  - guarded delete action

Important UI behavior:
- new employee creation does not preselect the current admin’s Business Unit in scope
- selected primary Business Unit is included automatically in the employee scope
- employee create, transfer, and Business Unit scope update flows ensure the
  employee has an assigned Office calendar when an eligible Office calendar is
  available
- employee detail removes the current-state panel
- employee detail places core data in one row and moves delete to the bottom
- employee detail shows active scoped project assignments in a grid with columns
  `Name`, `BU`, `From`, and `To`
- employee detail project-assignment visibility also includes active
  cross-office staffed projects as read-only `[Cross-Office]` rows so
  origin-office admins can see the employee's full project picture, including
  target-office projects outside the employee's home Office / Business Unit
- clicking the project name in that grid opens the related Project detail screen
  only when the current user is authorized for the target project scope; rows
  for unauthorized target-office projects remain visible as read-only text and
  cannot expose edit actions

### SCR-112 Employee Transfer

- Access: `TS_ADMIN_MASTER`
- Navigation:
  - visible as `Employee Transfers` inside the master-only System Management
    sub-navigation and overview cards
- Screen behavior:
  - standalone transfer workflow screen
  - source selection includes filters for Office, Primary BU, and Full Name text search
  - first load an active source employee
  - show read-only source summary
  - show read-only transfer-readiness section
  - show target setup only when the source employee has no active transfer
    blockers
- Target setup fields:
  - new employee code
  - target Office
  - target primary Business Unit
  - target additional Business Units
  - target role codes
  - archived source email preview
- Success state:
  - show read-only `Source Employee Archived` summary
  - show read-only `Target Employee Created` summary

## 8. Classification And Master Screens

### SCR-130 Client Management

- Access: `TS_ADMIN`
- Scope: Office
- Collection:
  - status filter
  - create client
  - show one row per Business Unit where the client has active projects
  - show the Business Unit name in the grid
  - show `Projects` as the number of active projects for that client and Business Unit row
  - show `Employees` as the number of distinct active employees with active assignments
    to those active projects for that Business Unit row
  - clicking `Projects` validates that the current admin is assigned to the row Business Unit
    before redirecting to `Project Management` with `Project Status = All` and the
    selected row Business Unit applied
  - if the caller is not assigned to the row Business Unit, the click shows an
    authorization error instead of a project list
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
  - routing-status visibility for approval-required General Charge Codes
- Detail:
  - edit Cost Center assignment, approver roles, lifecycle, validity, and behavior flags
  - show approval-routing status and warning text for selected ad-hoc approver roles
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
  - show active member count, dependent GCC count, and routing-coverage status
- Detail:
  - edit role code, name, description, members, and status
  - show dependent General Charge Codes and coverage warning text
  - prevent admins from setting referenced roles inactive or removing all active
    members
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
  - inline `Client` filter rendered beside the status filter row
  - create project
  - data grid columns:
    - `Business Unit` using the BU name
    - `Project Code`
    - `Project Name`
    - `Client`
    - `Status`
    - `Owner` using employee full name
    - `Manager` using employee full name
    - `Employees` showing the total distinct assigned employees, including inactive assignments
  - `Employees` counts include both normal Project Assignments and
    Cross-Office Staffing
  - clicking `Employees` opens project staffing management pre-filtered to
    that project with `status=All`
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
  - Client filter showing active Clients in the active Office
  - Project filter showing active Projects for the selected Client
  - changing the Client clears the selected Project filter
  - create project assignment
  - data grid shows Client, Project code, Project name, Employee, Start, End,
    and Status
  - employee display includes employee code plus full name
- Detail:
  - edit assignment dates and status
  - employee display includes employee code plus full name
  - guarded delete action
  - collection row link is the primary navigation path
  - detail layout matches the standalone create/edit pattern with bottom delete action

### SCR-191 Cross-Office Staffing Management

- Access: `TS_ADMIN`, `PROJECT_OWNER`, or `PROJECT_MANAGER`
- Scope:
  - `TS_ADMIN`: scoped target projects in the active Office
  - `PROJECT_OWNER`: staffing for owned target projects
  - `PROJECT_MANAGER`: staffing for managed target projects
- Collection:
  - status filter
  - Target Office filter
  - Client filter
  - Project filter
  - Origin Office filter
  - Employee filter
  - create cross-office staffing
  - data grid shows Target Office, Target BU, Client, Project code, Project
    name, Origin Office, Origin BU, Employee, Start, End, and Status
  - employee display includes employee code plus full name
- Create:
  - select target Project
  - show target Office and target BU as derived read-only values
  - when only one eligible target project exists in the current scope, prefill
    that project so Target Office and Target BU render immediately
  - when no target project is selected yet, Target Office still shows the
    current active Office as create-context guidance
  - select Origin Office
  - selecting Origin Office narrows the eligible active Employee list to that
    office only
  - select an eligible active Employee from that Origin Office
  - show Origin BU as read-only context
  - enter Assignment Start Date
  - enter Assignment End Date
  - enter Justification
  - select Status
- Detail:
  - edit assignment dates, justification, and status
  - employee/project/origin-office identity fields remain read-only
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
  - a withdrawn timesheet that has submission history may return to `CREATED`
    but delete remains blocked by the backend submission-history guard
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
  - top filter row:
    - inline `Client` selection filter positioned to the left of the existing
      status-filter buttons
    - selected client filter preserves the current status filter
  - status filters:
    - `All`
    - `Active`
    - `Closed`
    - `Draft`
  - summary grid columns:
    - `Name`
    - `Client`
    - `Status`
    - `Appr. Hours`
    - `Pend. Appr.`
    - `Missing TS`
  - project staffing-driven values such as missing-timesheet summaries include
    both normal Project Assignments and Cross-Office Staffing
  - project name opens:
    - editable System Management project detail for `TS_ADMIN`
    - editable owned-project System Management detail for `PROJECT_OWNER`
    - no link for `PROJECT_MANAGER`
  - approved-hours value opens the project-time report preloaded to that project
  - nonzero pending-timesheet values open the approval worklist prefiltered to
    that project
  - zero pending-timesheet values remain read-only text
  - missing-timesheet value opens the missing-timesheets report preloaded to that project

### SCR-220 Project Time Inquiry

- Access: `PROJECT_OWNER` or `PROJECT_MANAGER`
- features:
  - scoped live inquiry
  - project-related filters
  - totals
  - grouped Project Time report results with BU / Project and Week Start
    expand-collapse in the HTML viewer

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
    - project approval items follow the target project Office and scoped target
      Business Unit
    - General Charge Code approval items stay on the weekly-timesheet home
      Business Unit side
    - desktop filter layout uses three fields per row across two rows
    - page title remains `Approval Worklist`
    - pending approval grid with employee name, target, BU, approver name,
      TS submission date, and stalled-age visibility
    - recent outcomes section
    - read-only approval detail
    - compact top approval-context section in a single full-width block, with
      the related links box rendered below it
    - links to related timesheet and related project
  - approver variant:
    - pending approval list
    - no top summary count tiles
    - completed decision history section labeled `Last actions`
    - approval detail with the same compact context layout
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
- lower-priority administrative history cards render at the bottom of the hub:
  - `Archived Timesheets`
  - `Audit History`
  - `Integration Jobs`
- includes `Missing Timesheets by Project` for `PROJECT_OWNER`, `PROJECT_MANAGER`, and `TS_ADMIN`
- includes `Employee Utilization`, `Office / BU Time Summary`,
  `General Charge Code Usage`, and `Approval Turnaround` for `TS_ADMIN`

### SCR-410 Report Viewer

- Access: enforced per report
- supports report-specific filters and scoped result grids
- uses a shared stacked top layout:
  - `Filter Panel` renders first in a full-width section
  - `Report Totals` render below the filters in a second full-width section
  - filter fields and total cards try to fit into a single responsive row on
    wider screens
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
  - project staffing windows are derived from both normal Project Assignments
    and Cross-Office Staffing
  - CSV export is downloaded as an attachment from the browser

### SCR-421 Exportable Existing Reports

- Project Time:
  - `Export CSV` available from the shared report viewer actions
  - includes charged project time from valid cross-office staffed employees
  - the existing displayed `BU` field remains the weekly-timesheet home
    Business Unit unless a later reporting change says otherwise
  - HTML results use one grouped `Results Grid`
  - each visible `BU` / `Project` shows one summary row with expand/collapse
    access to grouped `Week Start` rows
  - each visible grouped `Week Start` row shows expand/collapse access to its
    detail lines
  - grouped results-grid columns are `BU`, `Project Code`, `Project`,
    `Week Start`, `Employee Code`, `Employee`, `Work Date`, `Hours`,
    `Billable`, `Approval State`, and `Comment`
  - row toggles use icon-only `+` and `-` controls
  - CSV export remains a flat detail download using the current filters
- Pending Approvals:
  - `Export CSV` available from the shared report viewer actions
  - `TS_ADMIN` project approval visibility follows the target project Office
    and scoped target Business Unit
  - result grid starts with `Week Start Date`
  - removes `Approval Item` and `Status` from the grid and CSV output
- Archived Timesheets:
  - `Export CSV` available from the shared report viewer actions
- Audit History:
  - `Export CSV` available from the shared report viewer actions
- Integration Jobs:
  - `Export CSV` available from the shared report viewer actions
- Employee Utilization:
  - `Export CSV` available from the shared report viewer actions
  - filters: `Business Unit`, `Employee`, `Work Date From`, `Work Date To`
  - result grid includes expected hours, worked hours, billable split, and
    utilization percent by employee
- Office / BU Time Summary:
  - `Export CSV` available from the shared report viewer actions
  - filters: `Business Unit`, `Work Date From`, `Work Date To`
  - result grid aggregates project-charged employee count, timesheet count,
    lines, total hours, and billable split by Office, Business Unit, and
    Project
  - result grid columns are `Office`, `BU Name`, `Project`, `Employees`,
    `Timesheets`, `Lines`, `Total Hours`, `Billable Hours`, and
    `Non-billable Hours`
  - General Charge Code lines do not produce rows in this report
  - valid cross-office staffing time is visible from:
    - the employee's origin-office summary when the weekly-timesheet home BU
      is in scope
    - the target-office summary when the charged project's BU is in scope and
      the employee belongs to another Office
  - selecting a Business Unit filters the report perspective, not just the row
    owner: rows remain included when the selected in-scope BU matches either
    the weekly-timesheet home BU or the charged target project's BU
  - out-of-scope Business Unit filter values must not broaden the server-side
    report query
  - cross-office project rows display the charged project's target Office and
    target Business Unit values in the grid
- General Charge Code Usage:
  - `Export CSV` available from the shared report viewer actions
  - filters: `Business Unit`, `General Charge Code`, `Employee`,
    `Work Date From`, `Work Date To`
  - result grid aggregates employee count, line count, total hours, and
    billable split by General Charge Code
- Approval Turnaround:
  - `Export CSV` available from the shared report viewer actions
  - `TS_ADMIN` project approval visibility follows the target project Office
    and scoped target Business Unit
  - filters: `Business Unit`, `Project`, `Approver`, `Status`,
    `Submitted From`, `Submitted To`
  - result grid shows approval-item timing, decision state, elapsed hours,
    and aging bucket

## 13. Detail Screen Delete Pattern

Where delete exists:
- the delete action is on the detail page
- the action is separate from edit
- the action does not cascade
- blocked deletes return an inline error on the same screen
