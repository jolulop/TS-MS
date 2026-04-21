# Phase II Scoped Employee Administration

## 1. Goal

Extend the Phase II backend foundation so Timesheet Administrators can manage employee core data, employee role assignments, and employee BU assignments within their assigned internal scope.

## 2. Scope

In scope:
- scoped TS Admin APIs for employee create/detail/update
- scoped TS Admin APIs for employee role assignment replacement
- scoped TS Admin APIs for employee BU assignment replacement
- audit coverage for employee email, role, and BU scope changes
- a forward-only schema fix for historical primary-BU assignment handling if required

Out of scope:
- employee import/export
- employee-management UI
- project, calendar, and timesheet admin flows
- PO/PM scoped employee administration

## 3. Source documents

- `docs/TS MAnagement functional specification v.5.1.docx`
- `docs/Authorization Matrix aligned to Functional Specification v5.1.docx`
- `docs/Business Rules Catalog v5.1.docx`
- `docs/Data Model - ERD v5.1.docx`
- `AGENTS.md`
- `PLANS.md`

## 4. Current state

- Internal session initialization and current-user scope loading are implemented.
- `USER` self access and scoped `TS_ADMIN` employee viewing are implemented.
- Employee/role/BU schema exists, but no write APIs exist yet.
- Current `employee_business_unit` primary constraint is too strict for preserving history when primary BU changes.

## 5. Target behavior

After this slice:
- `TS_ADMIN` can create employees directly in TS
- `TS_ADMIN` can update employee identity and status within scope
- `TS_ADMIN` can replace active role assignments within scope
- `TS_ADMIN` can replace active BU assignments within scope
- changing employee email, role assignments, or BU assignments writes audit records with before/after details
- non-admin users remain denied from these administration endpoints

## 6. Affected areas

Backend modules:
- `apps/auth`
- `apps/master_data`
- `apps/audit`
- `apps/reference_data`
- `config`

Frontend screens/features:
- none in this slice

Database / migrations:
- add forward-only migration to relax the primary BU uniqueness rule so it applies only to active primary assignments

APIs:
- add `/api/v1/admin/employees/`
- add `/api/v1/admin/employees/<id>/`
- add `/api/v1/admin/employees/<id>/roles/`
- add `/api/v1/admin/employees/<id>/business-units/`

Jobs / integrations:
- none

## 7. Business rules impacted

- only Timesheet Administrators may perform employee administration functions
- Timesheet Administrators may manage only employees in assigned Business Units
- Timesheet Administrators may assign employees to BUs only within their administration scope
- employee email is mandatory
- employee email must be unique among active employees
- role values come from reference data
- employee email changes, role changes, and BU scope changes must be auditable

## 8. Authorization impact

Roles affected:
- `TS_ADMIN`

Scope affected:
- assigned BU

Denied-access cases:
- non-admin caller attempts admin endpoint
- admin attempts to manage employee outside scoped BUs
- admin attempts to assign primary or secondary BU outside scoped BUs
- admin attempts to assign unknown or invalid role code

Backend enforcement points:
- admin service layer
- admin API views
- employee and BU policy helpers

## 9. Data model changes

- migration needed: yes
- tables affected:
- `employee_business_unit`
- `employee`
- `employee_role`
- `audit_log`
- constraints affected:
  - replace current single-primary constraint with active-primary-only constraint
- reference data seed changes:
  - none expected
- backfill needed: no

## 10. API changes

Endpoints to add/change:
- `POST /api/v1/admin/employees/`
- `PATCH /api/v1/admin/employees/<id>/`
- `PUT /api/v1/admin/employees/<id>/roles/`
- `PUT /api/v1/admin/employees/<id>/business-units/`

Request/response changes:
- JSON admin payloads for employee and BU create/update
- stable validation and access-denied error payloads

Error codes:
- `AUTH_ACCESS_DENIED`
- `BUSINESS_UNIT_NOT_FOUND`
- `BUSINESS_UNIT_OUT_OF_SCOPE`
- `EMPLOYEE_NOT_FOUND`
- `EMPLOYEE_EMAIL_REQUIRED`
- `EMPLOYEE_EMAIL_NOT_UNIQUE`
- `EMPLOYEE_PRIMARY_BU_OUT_OF_SCOPE`
- `EMPLOYEE_ROLE_INVALID`
- `EMPLOYEE_ROLE_OUT_OF_SCOPE`

OpenAPI updates required:
- no

## 11. UI changes

Screens to add/change:
- none

New actions:
- admin create/update employee
- admin replace roles
- admin replace BU assignments

Validation messages:
- JSON API validation messages only

Role visibility changes:
- none in templates yet

## 12. Audit and logging impact

Audit events to add/update:
- employee create
- employee email change
- employee status change
- employee role change
- employee BU scope change

Operational logs/metrics:
- none beyond existing logging

## 13. Implementation steps

1. Fix the primary BU assignment constraint for historical updates.
2. Add master-data management services for employees, roles, and BU assignments.
3. Add scoped TS Admin API endpoints.
4. Add audit helper support for before/after field changes.
5. Add tests for scope enforcement and write flows.
6. Run migrations, checks, lint, and tests.

## 14. Test plan

Unit tests:
- employee admin validation helpers
- TS Admin scope checks
- role and BU replacement logic

Integration tests:
- TS Admin creates employee in scoped BU
- non-admin denied employee admin APIs
- TS Admin cannot assign out-of-scope BU
- TS Admin replaces roles and BU assignments with audit records
- TS Admin cannot read or update out-of-scope employee

E2E tests:
- not required in this slice

Manual verification:
- create employee, update employee, replace roles, replace BU assignments

## 15. Risks and mitigations

- Risk: broadening admin access outside scoped BUs.
  - Mitigation: enforce scope in queries and payload validation.
- Risk: losing BU history while changing primary BU.
  - Mitigation: use a forward-only schema fix and append/update logic that preserves prior rows.
- Risk: role replacement causing duplicate same-day assignment collisions.
  - Mitigation: preserve matching active rows, deactivate removed rows, and reactivate same-day rows when safe.

## 16. Rollout / deployment notes

- feature flag needed: no
- migration sequencing:
  - apply constraint migration before exercising BU replacement flows
- seed sequencing:
  - existing reference seed only
- backward compatibility considerations:
  - existing read-only auth/session endpoints stay unchanged

## 17. Open questions / assumptions

- Assumption: this slice does not add Business Unit maintenance APIs; it only uses existing Business Units for scoped employee administration.
- Assumption: employee management remains API-only for now; no template/admin customization beyond model registration.
- Assumption: status updates will use existing reference values and will not add soft-delete behavior beyond status changes.

## 18. Definition of done

- code implemented
- migrations added and applied
- tests added/updated
- audit coverage added
- docs updated where required
- PLANS.md updated with current progress

## 19. Implementation status

Status:
- completed on 2026-04-21

Delivered:
- scoped TS Admin employee create/update APIs
- scoped TS Admin role replacement API
- scoped TS Admin BU assignment replacement API
- audit coverage for employee create, employee field updates, role changes, and BU scope changes
- forward-only migration for active primary-BU uniqueness

Validation run:
- `make format`
- `make lint`
- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py makemigrations master_data`
- `.venv/bin/python manage.py makemigrations --check`
- `.venv/bin/python manage.py migrate`
- `make test`
