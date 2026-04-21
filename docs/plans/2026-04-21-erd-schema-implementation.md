# ERD v5.1 Schema Implementation

## Goal

Implement the Phase 1 database schema from `docs/Data Model - ERD v5.1.docx` as forward-only Django models and migrations, keeping the milestone limited to structural persistence work. This plan does not implement business workflows, screens, or authorization behavior beyond schema relationships and core integrity constraints.

## Source Documents

- `docs/Data Model - ERD v5.1.docx`
- `docs/Business Rules Catalog v5.1.docx`
- `docs/TS MAnagement functional specification v.5.1.docx`
- `AGENTS.md`

## Scope

In scope:
- Replace the temporary Phase 1 reference-data shape with the ERD-aligned `ref_domain` and `ref_value` tables.
- Add Django apps and models for the ERD core entities.
- Add forward-only migrations for the new schema.
- Seed the minimum required reference-data domains and values needed by ERD foreign keys.
- Add or update tests covering schema-adjacent seed behavior and basic smoke validation.

Out of scope:
- Authentication/session logic.
- Authorization policies and scoped query services.
- Submit, approve, reject, reopen, archive, import, export, reminder, timer, and reporting behavior.
- Optional ERD extension tables explicitly marked as non-mandatory for first implementation.

## Affected Modules

- `apps/reference_data`
- `apps/organization`
- `apps/calendars`
- `apps/projects`
- `apps/timesheets`
- `apps/approvals`
- `apps/configuration`
- `apps/integrations`
- `apps/audit`
- `config/settings.py`
- `tests/`

## Schema Changes

Tables to add from the ERD core:
- `ref_domain`
- `ref_value`
- `business_unit`
- `employee`
- `employee_business_unit`
- `employee_role`
- `yearly_calendar`
- `calendar_period_rule`
- `calendar_special_day`
- `client`
- `internal_category`
- `cost_center`
- `general_charge_code`
- `project`
- `project_assignment`
- `weekly_timesheet`
- `timesheet_line`
- `timesheet_submission_cycle`
- `approval_item`
- `approval_action`
- `business_unit_configuration`
- `reminder_rule`
- `custom_attribute_definition`
- `custom_attribute_rule`
- `timesheet_line_attribute_value`
- `integration_job`
- `integration_job_error`
- `audit_log`

Tables intentionally deferred because the ERD marks them optional for first implementation:
- `employee_favorite_target`
- `timesheet_line_template`
- `time_capture_entry`
- `user_session`

## Constraint Strategy

Database-enforced in this milestone where practical:
- unique reference domain code
- unique reference value code within a domain
- unique employee code
- unique canonical email
- unique one-week timesheet per employee and week start date
- xor charging target on `timesheet_line`
- unique submission number within a weekly timesheet
- unique line attribute definition per timesheet line
- unique single BU configuration row per business unit
- key business-code uniqueness within BU-scoped masters

Deferred to model validation or future service/policy work when the ERD rule depends on cross-row or cross-domain semantics:
- role-specific validation for project owner / project manager assignments
- cross-BU consistency of related project master data
- no overlapping calendar period rules within a calendar
- approval-item scope-specific nullable field combinations driven by reference values
- lifecycle rules such as locked approved timesheets

## Seed Data Changes

Reference seed must move from ad hoc string domains to ERD-backed domains and values.

Minimum early domains/values to seed:
- `ROLE_CODE`: `USER`, `TS_ADMIN`, `PROJECT_OWNER`, `PROJECT_MANAGER`
- `EMPLOYEE_STATUS`: `ACTIVE`, `INACTIVE`
- `PROJECT_STATUS`: `DRAFT`, `ACTIVE`, `CLOSED`
- `TIMESHEET_STATUS`: `CREATED`, `SUBMITTED`, `APPROVED`, `REJECTED`, `ARCHIVED`
- `APPROVAL_STATUS`: `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`
- `APPROVAL_SCOPE_TYPE`: `LINE`, `PROJECT`, `GENERAL_CODE`
- `APPROVAL_ACTION_TYPE`: `APPROVE`, `REJECT`, `REOPEN`, `WITHDRAW`, `AUTO_APPROVE`
- `SPECIAL_DAY_TYPE`: `HOLIDAY`, `COMPANY_DAY`

Additional placeholder domains required to satisfy status/configuration foreign keys will also be created with conservative initial values.

## Tests To Add Or Update

- Update reference-data seed tests to assert domain and value creation.
- Keep the existing smoke tests green after the schema expansion.
- Add migration-check coverage through the existing validation commands rather than bespoke migration tests.

## Risks

- The ERD uses many `ref_value` foreign keys but does not fully enumerate every domain value set, so some seed domains will require conservative placeholder values for Phase 1 schema completeness.
- A few ERD rules are better enforced in PostgreSQL-specific constraints or service-layer validation later; forcing them prematurely would create brittle migrations.
- The current temporary reference-data migration will be superseded before the first commit, so the migration history can still be rewritten cleanly at this stage.
