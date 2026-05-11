# Integration API Specification v5.4

## 1. Purpose

Describe the currently implemented JSON API surface under `/api/v1`.

## 2. General Rules

- format: REST + JSON
- authorization is internal after session initialization
- row-level scope is enforced server-side
- business-rule failures return stable error codes
- not every server-rendered UI action has a matching JSON endpoint

## 3. Authentication And Session

### Auth

- `POST /api/v1/auth/session/initialize`
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/logout`

Behavior:
- initialize resolves the validated email into an internal session
- session payload exposes current employee, roles, Office, and Business Unit scope

## 4. Reference And Identity Endpoints

- `GET /api/v1/employees/`
- `GET /api/v1/employees/{employeeId}/`
- `GET /api/v1/business-units/`

These are read-oriented support endpoints for session and scope-aware UI behavior.

## 5. Admin Master Data Endpoints

All endpoints in this section are current-state admin endpoints. They are not a complete mirror of every UI action.

### Business Units

- `GET /api/v1/admin/business-units/`
- `POST /api/v1/admin/business-units/`
- `GET /api/v1/admin/business-units/{businessUnitId}/`
- `PATCH /api/v1/admin/business-units/{businessUnitId}/`

### Employees

- `POST /api/v1/admin/employees/`
- `PATCH /api/v1/admin/employees/{employeeId}/`
- `PUT /api/v1/admin/employees/{employeeId}/roles/`
- `PUT /api/v1/admin/employees/{employeeId}/business-units/`

### Clients

- `GET /api/v1/admin/clients/`
- `POST /api/v1/admin/clients/`
- `GET /api/v1/admin/clients/{clientId}/`
- `PATCH /api/v1/admin/clients/{clientId}/`

### Internal Categories

- `GET /api/v1/admin/internal-categories/`
- `POST /api/v1/admin/internal-categories/`
- `GET /api/v1/admin/internal-categories/{categoryId}/`
- `PATCH /api/v1/admin/internal-categories/{categoryId}/`

### Cost Centers

- `GET /api/v1/admin/cost-centers/`
- `POST /api/v1/admin/cost-centers/`
- `GET /api/v1/admin/cost-centers/{costCenterId}/`
- `PATCH /api/v1/admin/cost-centers/{costCenterId}/`

### Pricing Models

- `GET /api/v1/admin/pricing-models/`
- `POST /api/v1/admin/pricing-models/`
- `GET /api/v1/admin/pricing-models/{pricingModelId}/`
- `PATCH /api/v1/admin/pricing-models/{pricingModelId}/`

Request fields:
- `name`
- `description`

### Yearly Calendars

- `GET /api/v1/admin/yearly-calendars/`
- `POST /api/v1/admin/yearly-calendars/`
- `GET /api/v1/admin/yearly-calendars/{yearlyCalendarId}/`
- `PATCH /api/v1/admin/yearly-calendars/{yearlyCalendarId}/`

Request fields:
- `calendar_year`
- `calendar_name`
- `status_code`

### Calendar Special Days

- `GET /api/v1/admin/calendar-special-days/`
- `POST /api/v1/admin/calendar-special-days/`
- `GET /api/v1/admin/calendar-special-days/{specialDayId}/`
- `PATCH /api/v1/admin/calendar-special-days/{specialDayId}/`

Request fields:
- `yearly_calendar_id`
- `special_date`
- `day_type_code`
- `status_code`
- `default_general_charge_code_id`

### General Charge Codes

- `GET /api/v1/admin/general-charge-codes/`
- `POST /api/v1/admin/general-charge-codes/`
- `GET /api/v1/admin/general-charge-codes/{generalChargeCodeId}/`
- `PATCH /api/v1/admin/general-charge-codes/{generalChargeCodeId}/`

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

### Project Assignments

- `GET /api/v1/admin/project-assignments/`
- `POST /api/v1/admin/project-assignments/`
- `GET /api/v1/admin/project-assignments/{assignmentId}/`
- `PATCH /api/v1/admin/project-assignments/{assignmentId}/`

### Calendar Period Rules

- `GET /api/v1/admin/calendar-period-rules/`
- `POST /api/v1/admin/calendar-period-rules/`
- `GET /api/v1/admin/calendar-period-rules/{periodRuleId}/`
- `PATCH /api/v1/admin/calendar-period-rules/{periodRuleId}/`
- `business_unit_id` is required on create and update payloads
- `working_on_saturdays_flag` and `working_on_sundays_flag` are supported on create and update payloads
- `saturday_max_hours` and `sunday_max_hours` are supported on create and update payloads

## 6. Collection Filtering

Supported on lifecycle-managed admin collections:
- query parameter: `status`
- if omitted, return all rows visible in scope
- if provided, filter by the entity status code

Applied collections include:
- clients
- internal categories
- cost centers
- yearly calendars
- general charge codes
- projects
- project assignments
- calendar period rules

## 7. Timesheet Endpoints

- `GET /api/v1/timesheets/`
- `GET /api/v1/timesheets/{timesheetId}/`
- `PUT /api/v1/timesheets/{timesheetId}/lines/`
- `POST /api/v1/timesheets/{timesheetId}/submit/`
- `POST /api/v1/timesheets/{timesheetId}/withdraw/`

Admin timesheet actions:
- `POST /api/v1/admin/timesheets/{timesheetId}/reopen/`
- `POST /api/v1/admin/timesheets/{timesheetId}/withdraw/`
- `POST /api/v1/admin/timesheets/{timesheetId}/override-period-lock/`
- `POST /api/v1/admin/timesheets/{timesheetId}/archive/`
- `POST /api/v1/admin/timesheets/{timesheetId}/restore/`

## 8. Approval Endpoints

- `GET /api/v1/approvals/`
- `GET /api/v1/approvals/{approvalItemId}/`
- `POST /api/v1/approvals/{approvalItemId}/approve/`
- `POST /api/v1/approvals/{approvalItemId}/reject/`

## 9. Current Authorization Expectations

- `TS_ADMIN_MASTER` is used for Office UI flows, not a dedicated Office JSON admin API
- `TS_ADMIN` can call the implemented admin master-data endpoints inside active Office and Business Unit scope
- `PROJECT_MANAGER` is the approval-workflow API role
- `PROJECT_OWNER` and `PROJECT_MANAGER` gain reporting and inquiry access through the UI/report layer

## 10. Stable Error Code Highlights

### Projects

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

- `CALENDAR_PERIOD_RULE_CALENDAR_REQUIRED`
- `CALENDAR_PERIOD_RULE_CALENDAR_IMMUTABLE`
- `CALENDAR_PERIOD_RULE_EFFECTIVE_FROM_REQUIRED`
- `CALENDAR_PERIOD_RULE_EFFECTIVE_TO_REQUIRED`
- `CALENDAR_PERIOD_RULE_DATE_RANGE_INVALID`
- `CALENDAR_PERIOD_RULE_OVERLAP`

### Calendar Special Days

- `CALENDAR_SPECIAL_DAY_CALENDAR_REQUIRED`
- `CALENDAR_SPECIAL_DAY_CALENDAR_IMMUTABLE`
- `CALENDAR_SPECIAL_DAY_DATE_REQUIRED`
- `CALENDAR_SPECIAL_DAY_YEAR_MISMATCH`
- `CALENDAR_SPECIAL_DAY_NOT_UNIQUE`
- `CALENDAR_SPECIAL_DAY_GENERAL_CHARGE_CODE_OFFICE_MISMATCH`

## 11. Explicit Non-Endpoints

The following actions currently exist in the server-rendered UI but are not documented here as JSON endpoints:
- Office create/update/delete
- guarded delete actions for Business Units, Employees, Yearly Calendars, Calendar Special Days, Clients, Internal Categories, Cost Centers, and Pricing Models
