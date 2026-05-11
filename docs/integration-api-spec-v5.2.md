# Integration API Specification v5.2

Superseded by [integration-api-spec-v5.4.md](/home/jolulop/code/TS-MS/docs/integration-api-spec-v5.4.md).

Historical note only. Do not use this file as the current implementation source of truth.

## Purpose

This v5.2 note captures the Milestone 2 correction-pass API additions for System Management.

It originally targeted the legacy v5.1 integration/API document set and is preserved here only as a historical delta.

## Collection Filter Update

Insert into the existing System Management collection endpoints:

- Query parameter: `status`
- Behavior:
  - if omitted, API returns all visible rows
  - if supplied, API filters by the domain status value code for that entity
- Applies to:
  - `/api/v1/admin/clients/`
  - `/api/v1/admin/internal-categories/`
  - `/api/v1/admin/cost-centers/`
  - `/api/v1/admin/general-charge-codes/`
  - `/api/v1/admin/projects/`
  - `/api/v1/admin/project-assignments/`
  - `/api/v1/admin/calendar-period-rules/`

## New Endpoints

### Pricing Models

- `GET /api/v1/admin/pricing-models/`
- `POST /api/v1/admin/pricing-models/`
- `GET /api/v1/admin/pricing-models/{pricingModelId}/`
- `PATCH /api/v1/admin/pricing-models/{pricingModelId}/`

Request fields:
- `name`
- `description`

### Projects

- `GET /api/v1/admin/projects/`
- `POST /api/v1/admin/projects/`
- `GET /api/v1/admin/projects/{projectId}/`
- `PATCH /api/v1/admin/projects/{projectId}/`

Request fields:
- `business_unit_id`
- `project_code`
- `name`
- `description`
- `project_owner_employee_id`
- `project_manager_employee_id`
- `client_id`
- `internal_category_id`
- `cost_center_id`
- `pricing_model_id`
- `start_date`
- `end_date`
- `close_date`
- `billable_flag`
- `status_code`

Stable error codes to insert:
- `PROJECT_BUSINESS_UNIT_REQUIRED`
- `PROJECT_CODE_REQUIRED`
- `PROJECT_NAME_REQUIRED`
- `PROJECT_PRICING_MODEL_REQUIRED`
- `PROJECT_CODE_NOT_UNIQUE`
- `PROJECT_BUSINESS_UNIT_IMMUTABLE`
- `PROJECT_CLIENT_OFFICE_MISMATCH`
- `PROJECT_INTERNAL_CATEGORY_BU_MISMATCH`
- `PROJECT_COST_CENTER_OFFICE_MISMATCH`
- `PROJECT_PRICING_MODEL_OFFICE_MISMATCH`
- `PROJECT_OWNER_ROLE_INVALID`
- `PROJECT_MANAGER_ROLE_INVALID`
- `PROJECT_DATE_RANGE_INVALID`
- `PROJECT_CLOSE_DATE_INVALID`

### Project Assignments

- `GET /api/v1/admin/project-assignments/`
- `POST /api/v1/admin/project-assignments/`
- `GET /api/v1/admin/project-assignments/{assignmentId}/`
- `PATCH /api/v1/admin/project-assignments/{assignmentId}/`

Request fields:
- `project_id`
- `employee_id`
- `assignment_start_date`
- `assignment_end_date`
- `status_code`

Stable error codes to insert:
- `PROJECT_ASSIGNMENT_PROJECT_REQUIRED`
- `PROJECT_ASSIGNMENT_EMPLOYEE_REQUIRED`
- `PROJECT_ASSIGNMENT_PROJECT_IMMUTABLE`
- `PROJECT_ASSIGNMENT_EMPLOYEE_IMMUTABLE`
- `PROJECT_ASSIGNMENT_NOT_UNIQUE`
- `PROJECT_ASSIGNMENT_DATE_RANGE_INVALID`
- `PROJECT_ASSIGNMENT_PROJECT_CLOSED`
- `PROJECT_ASSIGNMENT_BEFORE_PROJECT_START`
- `PROJECT_ASSIGNMENT_AFTER_PROJECT_END`
- `PROJECT_ASSIGNMENT_AFTER_PROJECT_CLOSE`
- `PROJECT_ASSIGNMENT_EMPLOYEE_BU_SCOPE_INVALID`

### Calendar Period Rules

- `GET /api/v1/admin/calendar-period-rules/`
- `POST /api/v1/admin/calendar-period-rules/`
- `GET /api/v1/admin/calendar-period-rules/{periodRuleId}/`
- `PATCH /api/v1/admin/calendar-period-rules/{periodRuleId}/`

Request fields:
- `yearly_calendar_id`
- `effective_from`
- `effective_to`
- `monday_max_hours`
- `tuesday_max_hours`
- `wednesday_max_hours`
- `thursday_max_hours`
- `friday_max_hours`
- `status_code`

Stable error codes to insert:
- `CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED`
- `CALENDAR_PERIOD_RULE_CALENDAR_IMMUTABLE`
- `CALENDAR_PERIOD_RULE_EFFECTIVE_FROM_REQUIRED`
- `CALENDAR_PERIOD_RULE_EFFECTIVE_TO_REQUIRED`
- `CALENDAR_PERIOD_RULE_DATE_RANGE_INVALID`
- `CALENDAR_PERIOD_RULE_OVERLAP`

## Authorization Insertions

Insert into the admin authorization section:

- All endpoints above are `TS_ADMIN` only in v5.2.
- Row-level scope is still Business Unit based.
- The `status` filter must never broaden visibility beyond the caller’s Business Unit scope.
