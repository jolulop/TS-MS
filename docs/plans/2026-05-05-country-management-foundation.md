# Country Management Foundation

## 1. Goal

Introduce country as a first-class business dimension in the TS system, including a TS Admin-managed Country master, immutable mandatory country assignment on key entities, session-level active country context, and the cross-country staffing rules needed for projects, approvals, and employee timesheets.

## 2. Scope

In scope:
- add a `Country` master entity with active/inactive lifecycle
- add a `TS_ADMIN_MASTER` role for country lifecycle control only
- add mandatory immutable country assignment to the required business entities
- backfill existing data and seeds to `Holding`
- show active country context across authenticated UI screens
- update session initialization and authorization behavior for inactive countries
- add System Management country screens
- update existing JSON APIs and HTML management flows to include country data and validation
- preserve cross-country project assignment and charging behavior
- update audit payloads to include country context where relevant

Out of scope:
- hard deletion of country or country-bound records
- country switching during a session
- project assignment country ownership rules beyond the user request
- new Country JSON admin endpoints unless later approved

## 3. Source documents

- User change request dated `2026-05-05`
- [docs/functional-spec-v5.2.md](/home/jolulop/code/TS-MS/docs/functional-spec-v5.2.md)
- [docs/integration-api-spec-v5.2.md](/home/jolulop/code/TS-MS/docs/integration-api-spec-v5.2.md)
- [docs/ui-screen-spec-v5.2.md](/home/jolulop/code/TS-MS/docs/ui-screen-spec-v5.2.md)
- `docs/Data Model - ERD v5.1.docx`
- `docs/Authorization Matrix aligned to Functional Specification v5.1.docx`
- `docs/Business Rules Catalog v5.1.docx`
- [AGENTS.md](/home/jolulop/code/TS-MS/AGENTS.md)
- [PLANS.md](/home/jolulop/code/TS-MS/PLANS.md)

Note:
- The current approved repo documents do not define Country as a domain concept. For this task, the `2026-05-05` user change request is the source of truth for country behavior, with existing specs still governing all unchanged behavior.

## 4. Current state

- The system has no `Country` entity today.
- The internal session model carries employee identity, roles, and Business Unit scope only.
- Most administrative entities are Business Unit scoped, and several of them already depend directly on `BusinessUnit`.
- Timesheet behavior already depends on the employee's assigned calendar and the employee's Business Unit configuration.
- System Management HTML screens and admin JSON APIs exist for employees, clients, internal categories, cost centers, general charge codes, projects, project assignments, and calendar period rules.

## 5. Target behavior

After implementation:
- Country exists as a managed master entity with `id`, `name`, and `status`.
- `TS_ADMIN_MASTER` is the only role that can activate or deactivate countries.
- `TS_ADMIN_MASTER` cannot use regular country-bound administration features unless it also holds other business roles.
- `TS_ADMIN` can manage data only inside the active session country and cannot activate or deactivate countries.
- Each `BusinessUnit` belongs to exactly one Country.
- The following entities have a mandatory immutable `country_id` foreign key:
  - `BusinessUnit`
  - `YearlyCalendar`
  - `CalendarPeriodRule`
  - `Employee`
  - `Client`
  - `InternalCategory`
  - `CostCenter`
  - `GeneralChargeCode`
  - `Project`
- Country is derived automatically during session initialization from the matched employee and cannot be switched during the session.
- Authenticated screens show the active country as read-only context.
- Create/edit flows for the country-bound entities above show country as read-only, not editable, and do not allow empty country assignment.
- Country cannot be changed after entity creation.
- Employees can still be assigned to projects from other countries.
- Employees can still charge time to assigned projects from other countries.
- Employee timesheets continue to use the employee's own country-linked calendar and calendar period data.
- Project managers continue to review hours charged to their projects regardless of the employees' countries.
- Inactive countries remain visible to TS Admins, but no new records or edits are allowed within an inactive country.
- Non-TS Admin employees from inactive countries cannot initialize a session.
- `TS_ADMIN_MASTER` users from inactive countries can initialize a session to browse and reactivate country data.
- Regular `TS_ADMIN` users from inactive countries are denied session initialization.

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/auth`
- `apps/core`
- `apps/timesheets`
- `apps/audit`
- `apps/reference_data`

Frontend screens/features:
- access entry and session context display
- global authenticated app shell/header
- System Management country management list/detail
- all existing System Management create/edit forms for country-bound entities
- TS Management screens that show current user/session context
- approval and reports screens that display session context

Database / migrations:
- new `Country` table
- new foreign keys and data backfill on country-bound entities
- seed updates for country reference rows and existing dev data alignment

APIs:
- session payload updates
- existing master-data admin APIs updated to serialize and validate country fields
- no new Country API endpoints unless explicitly approved later

Jobs / integrations:
- import/export payload and validation impact to be assessed and updated where country-bound entities are involved

## 7. Business rules impacted

- Country is mandatory for all required country-bound entities.
- Country is immutable after creation for all required country-bound entities.
- Each employee belongs to exactly one country.
- Country is inferred from the matched employee at session initialization.
- Country is fixed for the session and displayed read-only.
- A country becoming inactive does not delete data.
- Inactive countries are browsable by TS Admin only.
- Only TS Admin can reactivate an inactive country.
- New records and edits inside inactive countries are blocked.
- Cross-country project assignment remains allowed.
- Cross-country project charging remains allowed.

## 8. Authorization impact

Roles affected:
- `USER`
- `TS_ADMIN`
- `TS_ADMIN_MASTER`
- `PROJECT_OWNER`
- `PROJECT_MANAGER`

Scope impact:
- Existing Business Unit scope remains in force unless a country rule narrows it further.
- Country becomes additional session and validation context.
- `TS_ADMIN_MASTER` is the only role allowed to activate or deactivate Country records.
- `TS_ADMIN` remains the country-scoped administrator for normal country-bound business data.
- Non-TS Admin login from an inactive country must be denied.
- Regular `TS_ADMIN` login from an inactive country must be denied.

Authorization notes:
- Country visibility must not bypass current Business Unit or project-based row-level rules.
- Country immutability must be enforced server-side in services and APIs.
- Inactive country write blocking must be enforced server-side for HTML and JSON flows.
- `TS_ADMIN_MASTER` permissions must stay narrower than `TS_ADMIN` for non-country business functions unless the same employee explicitly has both roles.

## 9. Data model changes

- migration needed: yes
- new table:
  - `Country`
- new required foreign keys:
  - `BusinessUnit.country`
  - `YearlyCalendar.country`
  - `CalendarPeriodRule.country`
  - `Employee.country`
  - `Client.country`
  - `InternalCategory.country`
  - `CostCenter.country`
  - `GeneralChargeCode.country`
  - `Project.country`
- no direct country field planned for:
  - `BusinessUnitConfiguration`
  - `CalendarSpecialDay`
  - `ProjectAssignment`
  - timesheets or timesheet lines
- backfill needed: yes
  - existing data maps to `Holding`
- seed data needed: yes
  - `Holding`
  - `España`
  - `Colombia`
  - `Perú`
  - `Argentina`
  - `México`

Consistency rules to enforce:
- `BusinessUnit.country` is mandatory
- `Employee.primary_business_unit.country` must match `Employee.country`
- `Employee.assigned_calendar.country` must match `Employee.country`
- `YearlyCalendar.business_unit.country` must match `YearlyCalendar.country`
- `CalendarPeriodRule.yearly_calendar.country` must match `CalendarPeriodRule.country`
- `Client.business_unit.country` must match `Client.country`
- `InternalCategory.business_unit.country` must match `InternalCategory.country`
- `CostCenter.business_unit.country` must match `CostCenter.country`
- `GeneralChargeCode.business_unit.country` must match `GeneralChargeCode.country`
- `Project.business_unit.country` must match `Project.country`

## 10. API changes

Endpoints to change:
- `/api/v1/auth/session/initialize`
- `/api/v1/auth/session`
- existing `/api/v1/admin/...` endpoints for affected country-bound entities

Request/response changes:
- session payload includes active country context
- session payload includes role support for `TS_ADMIN_MASTER`
- affected entity payloads include country data
- create requests require valid country assignment
- update requests reject country changes
- inactive country writes return stable business errors

Error codes to add or standardize:
- country required
- country immutable
- country inactive for write
- login denied because employee country is inactive
- country/entity mismatch with linked Business Unit or calendar

OpenAPI updates required:
- yes for changed endpoints

## 11. UI changes

Screens to add/change:
- global authenticated header/session summary shows active country
- access-entry follow-through shows country after login
- System Management Country Management list/detail pages
- existing create/edit screens for:
  - employees
  - yearly calendars
  - calendar period rules
  - clients
  - internal categories
  - cost centers
  - general charge codes
  - projects

UI rules:
- active country is shown read-only on authenticated screens
- country appears as a read-only field in the country-bound entity forms
- no editable country selector is shown in those forms
- inactive country records can be browsed by TS Admin
- inactive country records cannot be created or edited
- country management allows `TS_ADMIN_MASTER` to activate/inactivate countries
- country management allows `TS_ADMIN` to browse countries and their statuses only if needed for context, but not to change country lifecycle

## 12. Audit and logging impact

- add country context to relevant audit payloads where an entity already records audit activity
- country create/update/activate/inactivate actions require audit events
- session initialization denial for inactive country users requires audit coverage
- country mismatch and inactive-country write denials should be auditable where current policy requires denied sensitive action logging
- `TS_ADMIN_MASTER` country lifecycle actions must identify the actor role distinctly in audit history

## 13. Milestones

### Milestone 1
- schema and migrations for Country plus mandatory country foreign keys
- backfill existing data to `Holding`
- seed and dev-seed updates

### Milestone 2
- session/auth context updates
- inactive country login enforcement
- `TS_ADMIN_MASTER` role support in reference data and authorization helpers
- active country display in authenticated shell and session payload

### Milestone 3
- Country Management UI for `TS_ADMIN_MASTER`
- country lifecycle rules and audit coverage

### Milestone 4
- service and API validation for mandatory immutable country on affected entities
- country-scoped `TS_ADMIN` write enforcement
- HTML management form updates for read-only country display
- inactive country write blocking

### Milestone 5
- timesheet, approval, and reporting regression pass for cross-country project staffing rules
- targeted documentation updates and final regression coverage

## 14. Test plan

Unit tests:
- country immutability validators
- inactive country write blocking
- inactive country login blocking for non-TS Admin
- inactive country login blocking for regular `TS_ADMIN`
- `TS_ADMIN_MASTER` country lifecycle permission checks
- country consistency validation across linked Business Unit and calendar relationships

Integration tests:
- country create/update/activate/inactivate flows
- existing master-data APIs require and serialize country correctly
- employee session initialization returns active country context
- non-TS Admin denied when employee country is inactive
- regular `TS_ADMIN` denied when employee country is inactive
- `TS_ADMIN_MASTER` allowed when employee country is inactive
- create/update of affected entities reject empty or changed country

UI tests:
- authenticated shell shows active country
- country management screens render for `TS_ADMIN_MASTER` only
- affected System Management forms show read-only country
- inactive country can be browsed but not edited

Regression tests:
- cross-country project assignment still works
- employee can charge time to assigned project from another country
- project manager can review project time across employee countries
- employee timesheet still resolves assigned calendar and applicable period rule from the employee's own country-linked data

## 15. Risks and mitigations

- Risk: country and Business Unit become partially duplicated and drift apart.
  - Mitigation: add explicit service validations, backfill rules, and targeted tests for consistency.
- Risk: fixed session country conflicts with global TS Admin administration expectations.
  - Mitigation: use `TS_ADMIN_MASTER` for country lifecycle only and keep regular `TS_ADMIN` country-scoped.
- Risk: existing APIs and UI forms diverge on country handling.
  - Mitigation: implement shared validation in services and cover both JSON and HTML flows.
- Risk: inactive-country login rules unintentionally lock out required admin access.
  - Mitigation: add explicit tests for `TS_ADMIN_MASTER` access plus regular `TS_ADMIN` and non-admin denial.

## 16. Rollout / deployment notes

- feature flag needed: no
- backward compatibility: low, because schema and API payloads change
- deployment sequence:
  1. apply migration and backfill
  2. refresh reference and dev seed data
  3. deploy session/auth changes and service validation together
  4. run regression tests before enabling user validation

## 17. Open questions / assumptions

- Assumption: active country is shown on authenticated app screens only.
- Assumption: no new Country JSON admin endpoints are added in this phase; Country management is delivered through the server-rendered System Management UI while existing affected APIs are updated for country serialization and validation.
- Assumption: regular `TS_ADMIN` create/edit flows remain tied to the active session country and cannot target other countries.
- Assumption: `TS_ADMIN_MASTER` is a specialized role for country lifecycle only and does not automatically gain normal `TS_ADMIN` business administration permissions.

## 18. Definition of done

- plan file created and tracked in `PLANS.md`
- schema and backfill implemented
- session payload and authenticated shell show active country
- Country Management UI implemented
- affected services, APIs, and HTML forms enforce mandatory immutable country rules
- inactive country lifecycle behavior enforced and audited
- tests added or updated across unit, integration, and UI layers
- relevant docs and API specs updated

## 19. Implementation status

Status:
- completed

Completed milestone:
- Milestone 1: schema, migration/backfill, role seed foundation, and helper/dev-seed compatibility
- Milestone 2: session/auth country context, inactive-country login enforcement, `TS_ADMIN_MASTER` login allowance, and active-country shell display
- Milestone 3: `TS_ADMIN_MASTER`-only Country Management UI, country lifecycle update flows, navigation split, and country audit coverage
- Milestone 4: shared country write guards, immutable country validation, active-country-scoped management queries, read-only country form display, and inactive-country regression coverage
- Milestone 5: cross-country project assignment, timesheet charging, approval visibility, and report visibility regression coverage

Still pending:
- none

Validation completed for Milestones 1-4:
- `.venv/bin/python manage.py makemigrations --check`
- `.venv/bin/python manage.py migrate`
- `.venv/bin/python manage.py check`
- `.venv/bin/ruff check apps/master_data/models.py apps/master_data/admin.py apps/reference_data/seeds.py tests/helpers.py apps/master_data/management/commands/seed_dev_data.py apps/master_data/services.py apps/master_data/migrations/0004_country_foundation.py apps/auth/constants.py apps/auth/context.py apps/auth/services.py apps/auth/middleware.py apps/auth/views.py apps/core/views.py tests/test_auth_session.py tests/test_ui_shell.py`
- `.venv/bin/pytest tests/test_auth_session.py tests/test_ui_shell.py`
- `.venv/bin/pytest tests/test_employee_authorization.py tests/test_system_management_ui.py`
- `.venv/bin/pytest tests/test_ui_shell.py tests/test_system_management_ui.py`
- `.venv/bin/pytest tests/test_auth_session.py tests/test_employee_authorization.py`
- `.venv/bin/pytest tests/test_auth_session.py tests/test_system_management_ui.py tests/test_dev_seed.py`
- `.venv/bin/pytest tests/test_employee_admin.py tests/test_client_admin.py tests/test_internal_category_admin.py tests/test_cost_center_admin.py tests/test_general_charge_code_admin.py tests/test_phase5_system_management_extensions.py`
- `.venv/bin/ruff check apps/master_data/services.py apps/core/system_views.py tests/test_employee_admin.py tests/test_client_admin.py tests/test_system_management_ui.py`
- `.venv/bin/pytest tests/test_employee_admin.py tests/test_client_admin.py tests/test_system_management_ui.py`
- `.venv/bin/pytest tests/test_internal_category_admin.py tests/test_cost_center_admin.py tests/test_general_charge_code_admin.py tests/test_phase5_system_management_extensions.py`
- `.venv/bin/pytest tests/test_auth_session.py tests/test_ui_shell.py tests/test_employee_authorization.py`
- `.venv/bin/ruff check apps/master_data/services.py apps/core/system_views.py apps/timesheets/services.py tests/test_phase5_system_management_extensions.py tests/test_system_management_ui.py tests/test_timesheet_engine.py tests/test_ts_management_ui.py tests/test_reports_ui.py`
- `.venv/bin/pytest tests/test_phase5_system_management_extensions.py tests/test_system_management_ui.py tests/test_timesheet_engine.py tests/test_ts_management_ui.py tests/test_reports_ui.py`
- `.venv/bin/pytest tests/test_phase5_system_management_extensions.py tests/test_system_management_ui.py tests/test_timesheet_engine.py tests/test_ts_management_ui.py tests/test_reports_ui.py tests/test_auth_session.py tests/test_ui_shell.py tests/test_employee_authorization.py`
