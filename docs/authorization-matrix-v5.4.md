# Authorization Matrix v5.4

## 1. Principles

- deny by default
- authorization is internal after email validation
- scope must be enforced server-side
- Office context and Business Unit scope both matter

## 2. Role Matrix

| Capability | USER | PROJECT_OWNER | PROJECT_MANAGER | TS_ADMIN | TS_ADMIN_MASTER |
| --- | --- | --- | --- | --- | --- |
| Open own profile/session | Yes | Yes | Yes | Yes | Yes |
| View/edit own timesheets | Yes | Yes | Yes | Yes if self | Yes if self |
| Submit/withdraw own timesheets | Yes | Yes | Yes | Yes if self | Yes if self |
| Open My History | Yes | Yes | Yes | Yes | Yes |
| Open Project Time Inquiry | No | Yes | Yes | If also PO/PM or via reports | No direct role grant |
| Open Approval Worklist | No | No | Yes | No direct role grant | No |
| Approve/reject approval items | No | No | Yes, only assigned items | No direct role grant | No |
| Run Project Time report | No | Yes, owned projects | Yes, managed projects | Yes, scoped BUs | No direct role grant |
| Run admin reports | No | No | Pending Approvals only | Yes | No direct role grant |
| Manage Employees | No | No | No | Yes, scoped BUs | No |
| Manage Business Units | No | No | No | Yes, scoped BUs | No |
| Manage Clients | No | No | No | Yes, active Office | No |
| Manage Cost Centers | No | No | No | Yes, active Office | No |
| Manage Pricing Models | No | No | No | Yes, active Office | No |
| Manage Internal Categories | No | No | No | Yes, scoped BUs | No |
| Manage General Charge Codes | No | No | No | Yes, scoped BUs | No |
| Manage Projects | No | No | No | Yes, scoped BUs | No |
| Manage Project Assignments | No | No | No | Yes, scoped BUs | No |
| Manage Calendar Period Rules | No | No | No | Yes, scoped BUs | No |
| Manage Offices and Office configuration | No | No | No | No | Yes |

## 3. Scope Rules

### USER

- can act only on their own timesheets and history

### PROJECT_OWNER

- can access owned-project inquiry/reporting scope
- does not gain approval authority from ownership alone

### PROJECT_MANAGER

- can access managed-project inquiry/reporting scope
- can view and act on approval items assigned to them

### TS_ADMIN

- can administer records only inside:
  - the active Office
  - Business Unit scope, which is synchronized to all Business Units in the active Office while the employee holds `TS_ADMIN`
- can perform admin timesheet actions inside scoped Business Units

### TS_ADMIN_MASTER

- can manage Offices and Office configuration
- can bootstrap the first Business Unit and Office admin for a new Office
- does not implicitly inherit all `TS_ADMIN` behavior in the current UI/API

## 4. Special Cases

- Client, Cost Center, and Pricing Model visibility is Office-scoped.
- Internal Category, Project, Project Assignment, and Calendar Period Rule visibility is Business Unit scoped.
- Reports use per-report authorization rather than a single blanket rule.
