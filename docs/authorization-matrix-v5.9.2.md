# Authorization Matrix v5.9.2

## 1. Principles

- deny by default
- authorization is internal after email validation
- scope must be enforced server-side
- Office context and Business Unit scope both matter

## 2. Role Matrix

| Capability | USER | PROJECT_OWNER | PROJECT_MANAGER | TS_ADMIN | TS_ADMIN_MASTER |
| --- | --- | --- | --- | --- | --- |
| Open own profile from My info | Yes | Yes | Yes | Yes | Yes |
| Open dashboard from My info | No | Yes | Yes | Yes | Yes |
| View/edit own timesheets | Yes | Yes | Yes | Yes if self | Yes if self |
| Submit/withdraw own timesheets | Yes | Yes | Yes | Yes if self | Yes if self |
| Open merged My Timesheets history and missing-week view | Yes | Yes | Yes | Yes | Yes |
| Open Project Management UI | No | Yes, owned projects | Yes, managed projects | Yes, scoped BUs | No direct role grant |
| Open Project Detail from Project Management UI | No | Yes, owned projects editable | No | Yes, editable in scoped BUs | No direct role grant |
| Open Project Time Inquiry | No | Yes | Yes | If also PO/PM or via reports | No direct role grant |
| Open Approval Worklist | If matching GCC approver role | Yes, owned-project view plus matching GCC approver role items | Yes, plus matching GCC approver role items | Yes, scoped oversight plus any personal approver items | No direct role grant |
| Approve/reject approval items | If matching GCC approver role items | If matching GCC approver role items | Yes, assigned project items plus matching GCC approver role items | If matching GCC approver role items | If matching GCC approver role items |
| Open Reports Hub | No | Yes | Yes | Yes | No direct role grant |
| Run Project Time report | No | Yes, owned projects | Yes, managed projects | Yes, scoped BUs | No direct role grant |
| Run Missing Timesheets by Project report | No | Yes, owned projects | Yes, managed projects | Yes, scoped Office/BU project scope | No direct role grant |
| Run admin reports | No | No | Pending Approvals only | Yes | No direct role grant |
| Run Employee Utilization | No | No | No | Yes, scoped BUs | No direct role grant |
| Run Office / BU Time Summary | No | No | No | Yes, scoped BUs | No direct role grant |
| Run General Charge Code Usage | No | No | No | Yes, scoped BUs | No direct role grant |
| Run Approval Turnaround | No | No | No | Yes, scoped BUs | No direct role grant |
| Manage Employees | No | No | No | Yes, scoped BUs | No |
| Transfer Employees Across Offices | No | No | No | No | Yes |
| Manage Business Units | No | No | No | Yes, scoped BUs | No |
| Manage Clients | No | No | No | Yes, active Office | No |
| Manage Cost Centers | No | No | No | Yes, active Office | No |
| Manage Pricing Models | No | No | No | Yes, active Office | No |
| Manage Internal Categories | No | No | No | Yes, scoped BUs | No |
| Manage General Charge Codes | No | No | No | Yes, scoped BUs | No |
| Manage Projects | No | Yes, owned projects and owned-project create | No | Yes, scoped BUs | No |
| Manage Project Assignments | No | Yes, owned projects only | Yes, managed projects only | Yes, scoped BUs | No |
| Manage Calendar Period Rules | No | No | No | Yes, scoped BUs | No |
| Manage Countries | No | No | No | No | Yes |
| Manage Offices and Office configuration | No | No | No | No | Yes |

## 3. Scope Rules

### USER

- can act only on their own timesheets and history

### PROJECT_OWNER

- can access owned-project inquiry/reporting scope
- can open owned projects from the TS Project Management summary in editable System Management detail mode
- can create projects that are always owned by the current employee profile
- can create, edit, and delete assignments for owned projects only
- can review approval worklist items for owned projects
- does not gain approval authority from ownership alone

### PROJECT_MANAGER

- can access managed-project inquiry/reporting scope
- can create, edit, and delete assignments only for managed projects inside active Office and Business Unit scope
- can view and act on approval items assigned to them

### TS_ADMIN

- can administer records only inside:
  - the active Office
  - Business Unit scope, which is synchronized to all Business Units in the active Office while the employee holds `TS_ADMIN`
- can perform admin timesheet actions inside scoped Business Units
- can open approval oversight inside scoped Business Units
- can inspect approval detail and follow related links without gaining
  approve/reject authority from the admin role alone
- can run the advanced admin analytics reports only inside active Office and
  scoped Business Units

### TS_ADMIN_MASTER

- can manage Countries
- can manage Offices and Office configuration
- can transfer employees across Offices through the dedicated master workflow
- can bootstrap the first Business Unit and Office admin for a new Office
- does not implicitly inherit all `TS_ADMIN` behavior in the current UI/API

## 4. Special Cases

- Client, Cost Center, and Pricing Model visibility is Office-scoped.
- Internal Category, Project, Project Assignment, and Calendar Period Rule visibility is Business Unit scoped.
- Any active employee can gain General Charge Code approval authority through:
  - a selected existing TS internal role on the General Charge Code
  - a selected office ad-hoc General Charge Code approval role with active membership
- Reports use per-report authorization rather than a single blanket rule.
