# Phase III Classification Master Data

## 1. Goal

Implement the first Phase III master-data slice so Timesheet Administrators can manage the classification records that projects and time charging depend on: clients, internal categories, cost centers, and general charge codes.

## 2. Scope

In scope:
- scoped TS Admin APIs for clients
- scoped TS Admin APIs for internal categories
- scoped TS Admin APIs for cost centers
- scoped TS Admin APIs for general charge codes
- shared master-data validation and serialization patterns for these entities
- server-side BU-scope enforcement for all list/detail/write flows
- tests for create/update/list/detail scope behavior
- audit coverage for administrative writes if required by the existing audit conventions

Out of scope:
- yearly calendars, calendar period rules, and special days
- projects
- project assignments
- UI screens for Phase III master data
- imports/exports for these master tables
- Project Owner and Project Manager write flows

## 3. Source documents

- `docs/TS MAnagement functional specification v.5.1.docx`
- `docs/Use cases - Acceptance criteria v5..1.docx`
- `docs/Data Model - ERD v5.1.docx`
- `docs/Authorization Matrix aligned to Functional Specification v5.1.docx`
- `docs/Business Rules Catalog v5.1.docx`
- `docs/UI - Screen Specification  v5.1.docx`
- `AGENTS.md`
- `PLANS.md`

Note:
- The repository currently contains the approved spec documents as `.docx` files under `docs/`, not the markdown filenames referenced in `AGENTS.md`. This plan uses the current files present in the repo.

## 4. Current state

- The database schema for `client`, `internal_category`, `cost_center`, and `general_charge_code` already exists in `apps/master_data.models`.
- Internal session initialization and scoped `TS_ADMIN` authorization are implemented.
- Employee and BU administration endpoints already exist, giving us the policy and service patterns needed for admin master-data work.
- No write services or API endpoints exist yet for classification masters.
- Projects and timesheet flows are still unimplemented, so this slice can stay focused on foundational administrative data.

## 5. Target behavior

After this slice:
- `TS_ADMIN` can list and view clients, internal categories, cost centers, and general charge codes within assigned BU scope
- `TS_ADMIN` can create and update those records only within assigned BU scope
- non-admin users are denied these administrative endpoints
- status and date-window validation is enforced server-side
- the resulting data is ready to be referenced by later project and charging flows

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/auth`
- `apps/audit`
- `config`

Frontend screens/features:
- none in this slice

Database / migrations:
- maybe none, if the current ERD-backed schema is sufficient
- forward-only migrations only if implementation reveals missing constraints or status/date support gaps

APIs:
- add `/api/v1/admin/clients/`
- add `/api/v1/admin/clients/<id>/`
- add `/api/v1/admin/internal-categories/`
- add `/api/v1/admin/internal-categories/<id>/`
- add `/api/v1/admin/cost-centers/`
- add `/api/v1/admin/cost-centers/<id>/`
- add `/api/v1/admin/general-charge-codes/`
- add `/api/v1/admin/general-charge-codes/<id>/`

Jobs / integrations:
- none

## 7. Business rules impacted

- Timesheet Administrators act only within assigned Business Units
- projects later depend on valid `client`, `internal category`, and `cost center` records
- employees later can charge only to valid general charge codes for the work date
- general charge codes must preserve validity windows and active/inactive status semantics
- server-side authorization remains deny-by-default

## 8. Authorization impact

Roles affected:
- `TS_ADMIN`

Scope affected:
- assigned BU only

Denied-access cases:
- non-admin caller attempts classification-master admin endpoint
- admin attempts to create or update a record in a BU outside assigned scope
- admin attempts to view detail for a record outside assigned scope

Backend enforcement points:
- master-data service layer
- admin API views
- shared BU scope helpers

## 9. Data model changes

- migration needed: likely no for the initial slice
- tables affected:
  - `client`
  - `internal_category`
  - `cost_center`
  - `general_charge_code`
  - `audit_log`
- constraints affected:
  - none expected initially beyond existing uniqueness rules
- reference data seed changes:
  - maybe none, unless implementation reveals missing status or charge-type reference values
- backfill needed: no

## 10. API changes

Endpoints to add/change:
- `GET/POST /api/v1/admin/clients/`
- `GET/PATCH /api/v1/admin/clients/<id>/`
- `GET/POST /api/v1/admin/internal-categories/`
- `GET/PATCH /api/v1/admin/internal-categories/<id>/`
- `GET/POST /api/v1/admin/cost-centers/`
- `GET/PATCH /api/v1/admin/cost-centers/<id>/`
- `GET/POST /api/v1/admin/general-charge-codes/`
- `GET/PATCH /api/v1/admin/general-charge-codes/<id>/`

Request/response changes:
- JSON admin payloads for classification-master create/update
- consistent list/detail payload shape across master-data entities
- stable validation and access-denied error payloads

Error codes:
- `AUTH_ACCESS_DENIED`
- `BUSINESS_UNIT_OUT_OF_SCOPE`
- `CLIENT_NOT_FOUND`
- `INTERNAL_CATEGORY_NOT_FOUND`
- `COST_CENTER_NOT_FOUND`
- `GENERAL_CHARGE_CODE_NOT_FOUND`
- entity-specific required-field and uniqueness errors

OpenAPI updates required:
- no

## 11. UI changes

Screens to add/change:
- none

New actions:
- admin list/create/update clients
- admin list/create/update internal categories
- admin list/create/update cost centers
- admin list/create/update general charge codes

Validation messages:
- JSON API validation messages only

Role visibility changes:
- none in templates yet

## 12. Audit and logging impact

Audit events to add/update:
- create and update events for classification-master records if we follow the current admin-write audit pattern established in Phase II

Operational logs/metrics:
- none beyond existing logging

## 13. Implementation steps

1. Confirm the exact required fields and status semantics for each classification-master entity from the functional spec and UI spec.
2. Add shared scoped-admin service helpers for these master-data records.
3. Implement client endpoints and tests.
4. Implement internal-category endpoints and tests.
5. Implement cost-center endpoints and tests.
6. Implement general-charge-code endpoints and tests, including validity-window validation.
7. Add audit coverage where required.
8. Run checks, migrations check, and tests after each milestone.

## 14. Test plan

Unit tests:
- BU-scope validation helpers
- general charge code validity/date validation helpers
- entity serialization helpers if they become non-trivial

Integration tests:
- TS Admin can create and update each entity inside assigned BU scope
- non-admin callers are denied
- TS Admin cannot manage records outside assigned BU scope
- uniqueness and required-field validation errors are stable
- general charge code date validation is enforced

E2E tests:
- not required in this slice

Manual verification:
- create and update one record of each master-data type through the API

## 15. Risks and mitigations

- Risk: Phase III scope grows too fast by mixing calendars, projects, and assignments into one delivery.
  - Mitigation: keep this plan limited to classification masters only.
- Risk: inconsistent validation and payload shape across four related endpoints.
  - Mitigation: use shared service and serializer patterns.
- Risk: insufficient BU-scope enforcement leaks out-of-scope administrative data.
  - Mitigation: apply row-level scope in queries and validate BU in write payloads.
- Risk: general charge code validity rules become muddled with future timesheet rules.
  - Mitigation: implement only master-data validity checks now and defer charging behavior to later phases.

## 16. Rollout / deployment notes

- feature flag needed: no
- migration sequencing:
  - only if new constraints are discovered during implementation
- seed sequencing:
  - existing reference seed first
- backward compatibility considerations:
  - existing auth/session and employee-admin APIs stay unchanged

## 17. Open questions / assumptions

- Assumption: this first Phase III slice is API-only and intentionally does not add templates or browser workflows yet.
- Assumption: existing schema is sufficient for the initial CRUD scope unless implementation reveals missing constraints.
- Assumption: classification-master administrative writes should follow the same audit-friendly pattern established in Phase II, even though these entities are less workflow-sensitive than approvals or timesheets.

## 18. Definition of done

- code implemented
- migrations added only if needed
- tests added/updated
- audit coverage added where required
- docs updated where required
- PLANS.md updated with current progress

## 19. Implementation status

Status:
- completed

Completed milestone:
- Milestone 1: scoped TS Admin client list/detail/create/update APIs
- Milestone 2: scoped TS Admin internal-category list/detail/create/update APIs
- Milestone 3: scoped TS Admin cost-center list/detail/create/update APIs
- Milestone 4: scoped TS Admin general-charge-code list/detail/create/update APIs

Delivered in Milestone 1:
- client service-layer CRUD logic with BU-scope enforcement
- `/api/v1/admin/clients/` and `/api/v1/admin/clients/<id>/`
- client create/update audit coverage
- integration tests for scoped list/create/update and denied access

Delivered in Milestone 2:
- internal-category service-layer CRUD logic with BU-scope enforcement
- `/api/v1/admin/internal-categories/` and `/api/v1/admin/internal-categories/<id>/`
- internal-category create/update audit coverage
- integration tests for scoped list/create/update and denied access

Delivered in Milestone 3:
- cost-center service-layer CRUD logic with BU-scope enforcement
- `/api/v1/admin/cost-centers/` and `/api/v1/admin/cost-centers/<id>/`
- cost-center create/update audit coverage
- integration tests for scoped list/create/update and denied access

Delivered in Milestone 4:
- general-charge-code service-layer CRUD logic with BU-scope enforcement
- `/api/v1/admin/general-charge-codes/` and `/api/v1/admin/general-charge-codes/<id>/`
- general-charge-code create/update audit coverage
- general-charge-code date-range validation
- integration tests for scoped list/create/update, denied access, and invalid date ranges

Still pending:
- none in this plan

Validation run for Milestones 1-4:
- `make format`
- `make lint`
- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py makemigrations --check`
- `.venv/bin/python manage.py migrate`
- `make test`
- `make format-check`
