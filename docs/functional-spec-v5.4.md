# Functional Specification v5.4

## 1. Purpose

Define the current implemented behavior of the Timesheet Management System after the Office refactor and the expanded System Management feature set.

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

## 5. Organizational Model

### 5.1 Office

- Office is the top-level administrative entity.
- Office lifecycle uses status values such as `ACTIVE` and `INACTIVE`.
- Office configuration is owned at Office level.
- Only `TS_ADMIN_MASTER` can create, update, and delete Offices.
- Office creation bootstraps:
  - the Office
  - the Office configuration
  - an initial Business Unit
  - an initial Office administrator employee

### 5.2 Business Unit

- Business Units belong to exactly one Office.
- `TS_ADMIN` scope is Business Unit based.
- Business Units do not own operational configuration anymore.
- Business Unit detail shows inherited Office configuration as read-only.
- Business Units can be deleted only when no protected references remain.

### 5.3 Employees

- Employees belong to exactly one Office.
- Each employee has:
  - one primary Business Unit
  - one or more Business Units in scope
  - zero or more active roles
- The primary Business Unit must also be in Business Unit scope.
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

## 7. System Management Scope

### 7.1 Office-Scoped Masters

The following masters are managed at Office level:
- Offices
- Clients
- Cost Centers
- Pricing Models

### 7.2 Business-Unit-Scoped Masters

The following masters remain Business Unit scoped:
- Business Units
- Employees and Business Unit scope
- Internal Categories
- General Charge Codes
- Yearly Calendars
- Projects
- Project Assignments
- Calendar Period Rules

## 8. System Management Features

### 8.1 Offices

- `TS_ADMIN_MASTER` can create, edit, and guarded-delete Offices.
- Office detail shows:
  - general Office data
  - editable Office configuration
  - read-only Office administrators
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
- They keep lifecycle, approval, billing, and validity-window behavior.

### 8.7 Calendars And Special Days

- Yearly Calendars are managed in System Management.
- Yearly Calendars remain tied to a Business Unit and Office context.
- A Yearly Calendar can stay active even when the current date is outside the calendar year.
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
  - client must belong to the same Office
  - cost center must belong to the same Office
  - pricing model must belong to the same Office
  - internal category must belong to the same Business Unit
  - `end_date >= start_date`
  - `close_date >= start_date`

### 8.9 Project Assignments

- Project Assignments remain Business Unit scoped through the Project.
- Assignment creation is blocked for closed projects.
- The assigned employee must be active and in the project Business Unit scope.
- Assignment dates must stay inside the allowed project date window.

### 8.10 Calendar Period Rules

- Calendar Period Rules are managed in System Management.
- They remain tied to a Yearly Calendar and Business Unit/Office context.
- The system enforces:
  - `effective_to >= effective_from`
  - no overlapping rules within the same Yearly Calendar

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

Delete behavior:
- proceed only when protected dependencies do not exist
- do not cascade-delete business data
- show an error when referential integrity blocks the deletion

## 9. TS Management

### 9.1 My Timesheets

- Employees manage their own weekly Monday-to-Friday timesheets.
- One employee can have at most one weekly timesheet per week.
- Timesheet lines charge either:
  - a Project
  - a General Charge Code
- Weekend entry is not supported in the standard editor.

### 9.2 History

- Employees can view read-only historical timesheets.

### 9.3 Project Time Inquiry

- Available to `PROJECT_OWNER` and `PROJECT_MANAGER`.
- Shows live project-charged time in the caller’s owned or managed project scope.

## 10. Approvals

- The approval worklist is currently a `PROJECT_MANAGER` workflow.
- Project Managers can view and act on approval items assigned to them.
- Project Owners currently do not get approval authority from ownership alone.
- `TS_ADMIN` has reporting visibility over approvals but is not the primary approver role in the current UI workflow.

## 11. Reports

Implemented reports:
- My Timesheet History
- Project Time
- Pending Approvals
- Missing Timesheets
- Archived Timesheets
- Audit History
- Integration Jobs

Audience highlights:
- `USER`: My Timesheet History
- `PROJECT_OWNER`: Project Time
- `PROJECT_MANAGER`: Project Time, Pending Approvals
- `TS_ADMIN`: administrative reports across scoped Business Units

## 12. Audit Expectations

Audit coverage is required for sensitive state changes, including:
- employee identity and role changes
- Business Unit scope changes
- project ownership and management changes
- timesheet submit, withdraw, reopen, archive, restore
- approval approve and reject
- guarded administrative deletes

## 13. Out Of Scope For v5.4

- pricing calculations beyond storing a project Pricing Model
- Office-level JSON admin API
- cascade deletes for administrative masters
