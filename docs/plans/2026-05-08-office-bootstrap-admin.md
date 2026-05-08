# Office Bootstrap Admin

## 1. Goal

Allow `TS_ADMIN_MASTER` users to create a new Office together with the minimum bootstrap data needed to manage it: one Business Unit and one Office administrator employee.

## 2. Scope

In scope:
- extend the Office creation UI with bootstrap Business Unit and admin employee fields
- update Office creation service logic to create Office, then Business Unit, then admin employee in one transaction
- reuse the existing Business Unit and employee validation rules where applicable
- assign the created employee to the created Business Unit with `USER` and `TS_ADMIN` roles
- add regression tests proving the Office is immediately manageable after creation

Out of scope:
- changing Office update flows after creation
- creating a new Office JSON admin API
- widening `TS_ADMIN_MASTER` permissions outside the Office bootstrap workflow

## 3. Source documents

- 2026-05-08 user change request in this task
- `AGENTS.md`
- `docs/functional-spec-v5.2.md`
- `docs/ui-screen-spec-v5.2.md`
- `docs/plans/2026-05-05-country-management-foundation.md`

## 4. Current state

- Office creation currently creates only the Office and its configuration.
- Normal employee administration is `TS_ADMIN` and Business Unit scoped.
- Session initialization uses `employee.email` to determine the active Office, so a new Office with no employee cannot be used for normal administration.

## 5. Target behavior

- The Office create form collects:
  - Office fields
  - initial Business Unit fields
  - initial admin employee fields
- Submitting the form creates:
  1. the Office
  2. the initial Business Unit in that Office
  3. the initial admin employee in that Business Unit
- The created employee is active, belongs to the created Office, has the created Business Unit as primary scope, and receives `USER` plus `TS_ADMIN`.
- Existing Office update/detail behavior remains unchanged except for reflecting the created records naturally through related screens.

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/core`

Supporting artifacts:
- plan tracker
- tests

## 7. API changes

- no new Office JSON admin endpoint is introduced
- the existing server-rendered Office creation flow accepts the extra bootstrap fields

## 8. Authorization and audit

- `TS_ADMIN_MASTER` remains the only actor allowed to create Offices
- the created Office admin receives `USER` and `TS_ADMIN`
- audit events are required for Office, Office configuration, Business Unit, employee, role assignment, and Business Unit scope assignment creation

## 9. Tests

- Office create UI test covering Office + Business Unit + admin creation
- Office create UI test proving the created admin can initialize a session and see the created Business Unit
- regression coverage for Office update flow after the create form expands

## 10. Risks and assumptions

- Assumption: “timesheet owner for that office” means an initial internal administrator employee for normal Office-scoped management, implemented as `USER` + `TS_ADMIN`.
- Assumption: the bootstrap Business Unit and bootstrap admin default to `ACTIVE` status to keep the new Office immediately usable when the Office itself is active.
- Risk: this introduces a privileged bootstrap path for Business Unit and employee creation outside the normal `TS_ADMIN` current-office scope checks, so the implementation must keep the scope fixed to the newly created Office and Business Unit only.

## 11. Implementation status

Status:
- completed

Delivered:
- Office create form now captures initial Business Unit and initial admin employee fields
- Office creation now creates Office, Office configuration, initial Business Unit, and initial admin employee in one transaction
- created admin is assigned to the created Business Unit and receives `USER` plus `TS_ADMIN`
- regression test coverage proves the created admin can initialize a session and open Business Unit management for the new Office
