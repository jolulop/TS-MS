# UI Screen Specification v5.4

## 1. Purpose

Describe the current server-rendered UI screens and behaviors implemented in the repository.

## 2. Navigation

Top-level areas:
- `System Management`
- `TS Management`
- `Approvals`
- `Reports`
- `Profile`

Role-aware visibility applies to menus and actions.

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

## 4. Shared Collection Behavior

- Collections use a shared administrative shell.
- Rows expose an explicit `Open / Edit` action.
- Status-managed collections expose a status filter bar where applicable.
- Create forms live on collection screens.
- Update and delete actions live on detail screens.

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
  - create Office
  - require Country selection
  - capture Office configuration
  - capture bootstrap Business Unit data
  - capture bootstrap admin user data
- Detail:
  - edit parent Country
  - edit general Office data
  - edit Office configuration
  - show read-only Office administrators
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

### SCR-140 Internal Category Management

- Access: `TS_ADMIN`
- Scope: Business Unit
- Collection:
  - status filter
  - create internal category
- Detail:
  - edit category fields
  - guarded delete action

### SCR-150 Cost Center Management

- Access: `TS_ADMIN`
- Scope: Office
- Collection:
  - status filter
  - create cost center
- Detail:
  - edit cost center fields
  - guarded delete action

### SCR-155 Pricing Model Management

- Access: `TS_ADMIN`
- Scope: Office
- Collection:
  - create pricing model
- Detail:
  - edit name and description
  - guarded delete action

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

- Access: `TS_ADMIN`
- Scope: Business Unit
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

### SCR-190 Project Assignment Management

- Access: `TS_ADMIN`
- Scope: Project Business Unit
- Collection:
  - status filter
  - create project assignment
- Detail:
  - edit assignment dates and status

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

## 10. TS Management Screens

### SCR-200 My Timesheets

- Access: authenticated `USER`
- features:
  - view current/available weekly timesheets
  - header-level `Week Start Date` selector and `Create Timesheet` action
  - create flow opens the weekly editor directly for the selected date
  - open weekly timesheets into the dedicated edit/detail screen
  - submit
  - withdraw if allowed
  - delete draft timesheets only when deletion is allowed by backend rules

### SCR-210 My History

- Access: authenticated `USER`
- features:
  - read-only historical list
  - open a historical timesheet detail

### SCR-220 Project Time Inquiry

- Access: `PROJECT_OWNER` or `PROJECT_MANAGER`
- features:
  - scoped live inquiry
  - project-related filters
  - totals

## 11. Approval Screens

### SCR-300 Approval Worklist

- Access: `PROJECT_MANAGER`
- features:
  - pending approval list
  - approval detail
  - approve
  - reject

## 12. Report Screens

### SCR-400 Reports Hub

- Access: role-based by report
- cards show:
  - title
  - summary
  - audience
  - scoped count

### SCR-410 Report Viewer

- Access: enforced per report
- supports report-specific filters and scoped result grids

## 13. Detail Screen Delete Pattern

Where delete exists:
- the delete action is on the detail page
- the action is separate from edit
- the action does not cascade
- blocked deletes return an inline error on the same screen
