# System Management Delete Actions

## 1. Goal

Allow `TS_ADMIN` users to delete transient Employee, Business Unit, Internal Category, and Cost Center records from System Management when those records are not in real downstream use, so test-data cleanup can happen from the UI without bypassing safeguards.

## 2. Scope

In scope:
- add delete buttons to the Employee and Business Unit detail screens
- add delete buttons to the Internal Category and Cost Center detail screens
- add guarded delete service methods for Employees, Business Units, Internal Categories, and Cost Centers
- preserve audit history while allowing deletion of lightweight management records
- add regression tests for successful and blocked deletes

Out of scope:
- schema changes
- broad cascading deletes across transactional history
- adding delete actions to other System Management entities beyond these four

## 3. Source documents

- 2026-05-08 user request in this task
- `AGENTS.md`
- `PLANS.md`
- existing Office delete implementation

## 4. Current state

- Office detail already has a guarded delete action in System Management.
- Employee and Business Unit detail screens do not expose delete actions.
- A naive Business Unit delete is blocked even for freshly created data because audit rows and admin-scope assignment rows hold protected references.

## 5. Target behavior

- Employee detail shows a `Delete Employee` action.
- Business Unit detail shows a `Delete Business Unit` action.
- Internal Category detail shows a `Delete Internal Category` action.
- Cost Center detail shows a `Delete Cost Center` action.
- Deletion is allowed only for records with no protected operational usage.
- Lightweight management links created for administration bootstrap or scope maintenance may be cleaned first:
  - employee role assignments
  - employee Business Unit scope assignments
  - Business Unit-scoped role/scope links
  - audit-log Business Unit foreign keys are cleared while the audit rows remain
- If the record is still in use by employees, projects, calendars, timesheets, approvals, audit actor history, or other protected records, deletion is blocked with a clear message.

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/core`

Supporting artifacts:
- plan tracker
- UI tests

## 7. Authorization and audit

- `TS_ADMIN` remains required for Employee and Business Unit deletion.
- row-level scope still applies before any delete is attempted.
- delete operations must write audit events for the deleted entity and for any cleaned lightweight assignment rows.

## 8. Tests

- Employee UI delete succeeds for an unused managed employee
- Employee UI delete is blocked when the employee is still referenced
- Business Unit UI delete succeeds for a newly created unused Business Unit
- Business Unit UI delete is blocked when the Business Unit is still referenced by an employee
- Internal Category UI delete succeeds for an unused category
- Internal Category UI delete is blocked when the category is still referenced by a project
- Cost Center UI delete succeeds for an unused cost center
- Cost Center UI delete is blocked when the cost center is still referenced by a project

## 9. Risks and assumptions

- Assumption: for this request, physical delete is acceptable only for unused master data; transactional or historical dependencies must still block deletion.
- Risk: Business Unit delete requires disassociating `AuditLog.business_unit` to preserve audit rows while removing the deleted Business Unit row. The entity-level audit rows remain intact through `entity_name` and `entity_id`.

## 10. Implementation status

Status:
- completed

Delivered:
- Employee detail now includes a guarded `Delete Employee` action
- Business Unit detail now includes a guarded `Delete Business Unit` action
- Internal Category detail now includes a guarded `Delete Internal Category` action
- Cost Center detail now includes a guarded `Delete Cost Center` action
- delete services clean lightweight management links first where needed, then block if protected operational dependencies still exist
- UI regression coverage now proves both successful cleanup and blocked in-use deletes
