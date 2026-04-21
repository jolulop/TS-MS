# Phase II Employee Access and Internal Authorization Foundation

## 1. Goal

Start Phase II with the smallest useful backend slice that turns the existing employee, role, and Business Unit schema into an operational internal access layer. This phase will initialize internal sessions from a validated email, load employee roles and BU scope from TS data, and enforce deny-by-default authorization in backend endpoints.

## 2. Scope

In scope:
- internal session initialization using a validated email input
- active employee lookup and denial handling
- loading active employee roles and active BU scope from TS data
- centralized authorization policy helpers for employee and BU access
- minimal protected endpoints for current session, employee access, and BU scope
- basic admin registration for employee/role/BU/reference-data models to support local development
- audit logging for session-identification success and denial cases

Out of scope:
- external identity provider or ACL integration
- full employee-management UI workflows
- project, timesheet, approval, and report authorization
- row-level policy coverage for all entities
- full permission matrix implementation across every module

## 3. Source documents

- `docs/TS MAnagement functional specification v.5.1.docx`
- `docs/Authorization Matrix aligned to Functional Specification v5.1.docx`
- `docs/Business Rules Catalog v5.1.docx`
- `docs/Data Model - ERD v5.1.docx`
- `AGENTS.md`
- `PLANS.md`

## 4. Current state

- The Phase I scaffold and ERD core schema are committed.
- Employee, role, BU, and audit tables exist, but there is no runtime session initialization or internal authorization layer yet.
- The app exposes only a health endpoint and a home page.
- There are no protected API endpoints and no central current-user context.

## 5. Target behavior

After this slice:
- the system can receive a validated email and create an internal TS session if it matches exactly one active employee
- the system denies access if no active employee matches the validated email
- the system loads effective active roles and active BU scope from TS data on each authenticated request
- backend endpoints can enforce deny-by-default access using centralized policy helpers
- a logged-in user can fetch their own session/profile context
- a TS Admin can view employees within assigned BU scope
- a normal user can access only their own employee detail
- BU access is limited to the employee’s current internal scope

## 6. Affected areas

Backend modules:
- `apps/auth`
- `apps/audit`
- `apps/master_data`
- `apps/reference_data`
- `config`

Frontend screens/features:
- none beyond API/session behavior in this slice

Database / migrations:
- no schema changes planned unless implementation reveals a missing small support field

APIs:
- add `/api/v1/auth/session/initialize`
- add `/api/v1/auth/session`
- add `/api/v1/auth/logout`
- add `/api/v1/employees/`
- add `/api/v1/employees/<id>/`
- add `/api/v1/business-units/`

Jobs / integrations:
- none

## 7. Business rules impacted

- external validation is used only once to validate the user email at access time
- TS identifies the user internally using `employee.email`
- all post-login authorization is internal to TS
- roles come from TS data, not the external validation system
- deny by default
- row-level scope must be enforced server-side
- TS Admin scope is limited to assigned Business Units
- a normal employee cannot access other employees’ records unless an internal role permits it

## 8. Authorization impact

Roles affected:
- `USER`
- `TS_ADMIN`
- `PROJECT_OWNER`
- `PROJECT_MANAGER`

Scope affected:
- self
- assigned BU

Denied-access cases to enforce now:
- no internal session
- validated email does not match an active employee
- inactive employee
- employee has no active roles
- non-admin employee requesting another employee record
- employee requesting BU data outside internal scope

Backend enforcement points:
- session initialization service
- request current-user loader
- employee list/detail endpoints
- BU list endpoint

## 9. Data model changes

- migration needed: no, expected
- tables affected:
  - `employee`
  - `employee_role`
  - `employee_business_unit`
  - `business_unit`
  - `audit_log`
- constraints affected: none planned
- reference data seed changes:
  - add `AUDIT_ACTION_TYPE.LOGIN_IDENTIFICATION` for internal session-identification audit events
- backfill needed: no

## 10. API changes

Endpoints to add/change:
- `POST /api/v1/auth/session/initialize`
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/logout`
- `GET /api/v1/employees/`
- `GET /api/v1/employees/<id>/`
- `GET /api/v1/business-units/`

Request/response changes:
- JSON request for validated email input
- structured JSON session payload with employee identity, active roles, and BU scope
- structured error payloads with stable auth/access error codes

Error codes:
- `AUTH_EMPLOYEE_NOT_FOUND`
- `AUTH_EMPLOYEE_INACTIVE`
- `AUTH_DUPLICATE_EMPLOYEE_EMAIL`
- `AUTH_NO_ACTIVE_ROLE`
- `AUTH_SESSION_REQUIRED`
- `AUTH_ACCESS_DENIED`

OpenAPI updates required:
- no, not yet in repo

## 11. UI changes

Screens to add/change:
- none required for this slice

New actions:
- session initialize
- session inspect
- logout

Validation messages:
- stable auth/session failure messages via JSON errors

Role visibility changes:
- none in templates yet

## 12. Audit and logging impact

Audit events to add/update:
- login-identification success after validated email match
- login-identification denial when email does not match or cannot initialize

Operational logs/metrics:
- no extra metrics in this slice beyond existing structured logging

## 13. Implementation steps

1. Create the Phase II auth module and current-user context loading.
2. Implement session initialization service using validated email and active employee lookup.
3. Implement centralized authorization policies for employee and BU access.
4. Add protected API endpoints for current session, employees, and business units.
5. Register employee/BU/role/reference-data models in Django admin for local management.
6. Add tests for session initialization, denial cases, and scoped employee access.
7. Run checks, migration checks, migrate, and tests.

## 13A. Progress update

Completed:
- added the internal auth app and request-level current-user loading
- implemented session initialization from validated email with internal employee lookup
- added centralized employee/BU access policies
- added protected JSON endpoints for session, employee access, and BU scope
- added admin registration for reference data, business units, employees, BU assignments, and roles
- added audit writing for session-identification success and denial
- updated reference seed data with `LOGIN_IDENTIFICATION`
- validated with checks, migration checks, migrate, seed, and tests

## 14. Test plan

Unit tests:
- session initialization success and denial logic
- active role / active BU scope resolution
- employee access policy decisions

Integration tests:
- initialize session from validated email and fetch current session
- deny access when email has no active employee
- deny employee detail access outside scope
- allow TS Admin employee list only within assigned BU scope

E2E tests:
- not required in this slice

Manual verification:
- initialize session with a seeded test employee
- inspect current session payload
- hit protected endpoints with and without session

## 15. Risks and mitigations

- Risk: accidentally broadening employee visibility for PO/PM users.
  - Mitigation: keep this slice narrow and allow only self or TS Admin employee access.
- Risk: session data becoming stale if roles or BU assignments change.
  - Mitigation: load effective roles and BU scope from the database on each request instead of caching permissions in session.
- Risk: ambiguity between `email` and `canonical_email`.
  - Mitigation: normalize input and use the safest exact internal match strategy, documenting the assumption.

## 16. Rollout / deployment notes

- feature flag needed: no
- migration sequencing: none expected
- seed sequencing: existing reference seed only
- backward compatibility considerations:
  - existing scaffold endpoints remain unchanged

## 17. Open questions / assumptions

- Assumption: in this first auth slice, an employee must have at least one active internal role to complete session initialization, as the authorization matrix calls this out explicitly.
- Assumption: employee list access is limited to TS Admin only in this slice; PO/PM scoped employee visibility will be added later only where required by project/timesheet flows.
- Assumption: validated email matching will use a normalized internal lookup compatible with the current `canonical_email` column.

## 18. Definition of done

- code implemented
- tests added/updated
- migrations checked
- audit coverage added for session identification
- docs updated where required
- PLANS.md updated with current progress reference
