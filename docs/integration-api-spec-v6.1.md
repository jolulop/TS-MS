# Integration API Specification v6.1

## 1. Purpose

Describe the currently implemented JSON API surface under `/api/v1`.

No JSON API versioning change was introduced in the v6.1 documentation promotion. The main implemented deltas in the current surface are:

- the user-initiated `Copy Prev. Week` flow on the existing timesheet create surface
- `TS_ADMIN_MASTER` JSON parity for Country administration
- `TS_ADMIN_MASTER` JSON parity for Office administration
- completed `TS_ADMIN` employee admin parity for list, detail, and guarded
  delete on top of the existing create/update/role/BU endpoints
- guarded `DELETE` support across the current Country, Office, and master-data
  admin endpoints where the service layer already supports safe deletion
- richer General Charge Code and GCC approval-role admin payloads for routing
  governance and validation

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
- initialize resolves a trusted external email claim into an internal session
- session payload exposes current employee, roles, Office, and Business Unit scope

Authentication provider behavior:
- `development-email` is the local-only adapter. It accepts JSON
  `validated_email` or the HTML access-entry field only when development auth
  is enabled and `TSMS_ENVIRONMENT` is not `production`.
- `trusted-header` is the production adapter contract for Google SSO / Azure
  ingress. The ingress layer authenticates the user and forwards the trusted
  email claim in the configured server-side header, defaulting to
  `HTTP_X_MS_CLIENT_PRINCIPAL_NAME`.
- Production deployments must not accept arbitrary browser-posted
  `validated_email` values.
- After the email claim is accepted, TS resolves roles, Office, and Business
  Unit scope from internal TS data only.

## 4. Reference And Identity Endpoints

- `GET /api/v1/employees/`
- `GET /api/v1/employees/{employeeId}/`
- `GET /api/v1/business-units/`

These are read-oriented support endpoints for session and scope-aware UI behavior.

## 5. Admin Master Data Endpoints

All endpoints in this section are current-state admin endpoints. They are not a complete mirror of every UI action.

### Countries

- `GET /api/v1/admin/countries/`
- `POST /api/v1/admin/countries/`
- `GET /api/v1/admin/countries/{countryId}/`
- `PATCH /api/v1/admin/countries/{countryId}/`
- `DELETE /api/v1/admin/countries/{countryId}/`

Request fields:
- `country_code`
- `country_name`
- `status_code`

### Offices

- `GET /api/v1/admin/offices/`
- `POST /api/v1/admin/offices/`
- `GET /api/v1/admin/offices/{officeId}/`
- `PATCH /api/v1/admin/offices/{officeId}/`
- `DELETE /api/v1/admin/offices/{officeId}/`

Request fields:
- `country_id`
- `office_name`
- `status_code`
- `approval_mode_code`
- `allow_employee_withdraw_flag`
- `timesheet_cutoff_date`
- `count_non_billable_in_daily_limit_flag`
- `archive_after_years`
- `enable_timer_flag`
- `enable_leave_integration_flag`
- `enable_copy_previous_week_flag`
- `bootstrap_bu_code`
- `bootstrap_bu_name`
- `bootstrap_bu_description`
- `bootstrap_admin_employee_code`
- `bootstrap_admin_full_name`
- `bootstrap_admin_email`

### Business Units

- `GET /api/v1/admin/business-units/`
- `POST /api/v1/admin/business-units/`
- `GET /api/v1/admin/business-units/{businessUnitId}/`
- `PATCH /api/v1/admin/business-units/{businessUnitId}/`
- `DELETE /api/v1/admin/business-units/{businessUnitId}/`

### Employees

- `GET /api/v1/admin/employees/`
- `POST /api/v1/admin/employees/`
- `GET /api/v1/admin/employees/{employeeId}/`
- `PATCH /api/v1/admin/employees/{employeeId}/`
- `DELETE /api/v1/admin/employees/{employeeId}/`
- `PUT /api/v1/admin/employees/{employeeId}/roles/`
- `PUT /api/v1/admin/employees/{employeeId}/business-units/`

Collection query params:
- `status`

Delete behavior:
- guarded delete only
- blocked deletes return a structured business error such as
  `EMPLOYEE_DELETE_BLOCKED`
- self-delete remains blocked with `EMPLOYEE_DELETE_SELF_BLOCKED`
- blocked delete attempts are audited

### Clients

- `GET /api/v1/admin/clients/`
- `POST /api/v1/admin/clients/`
- `GET /api/v1/admin/clients/{clientId}/`
- `PATCH /api/v1/admin/clients/{clientId}/`
- `DELETE /api/v1/admin/clients/{clientId}/`

### Internal Categories

- `GET /api/v1/admin/internal-categories/`
- `POST /api/v1/admin/internal-categories/`
- `GET /api/v1/admin/internal-categories/{categoryId}/`
- `PATCH /api/v1/admin/internal-categories/{categoryId}/`
- `DELETE /api/v1/admin/internal-categories/{categoryId}/`

### Cost Centers

- `GET /api/v1/admin/cost-centers/`
- `POST /api/v1/admin/cost-centers/`
- `GET /api/v1/admin/cost-centers/{costCenterId}/`
- `PATCH /api/v1/admin/cost-centers/{costCenterId}/`
- `DELETE /api/v1/admin/cost-centers/{costCenterId}/`

### Pricing Models

- `GET /api/v1/admin/pricing-models/`
- `POST /api/v1/admin/pricing-models/`
- `GET /api/v1/admin/pricing-models/{pricingModelId}/`
- `PATCH /api/v1/admin/pricing-models/{pricingModelId}/`
- `DELETE /api/v1/admin/pricing-models/{pricingModelId}/`

Request fields:
- `name`
- `description`

### Yearly Calendars

- `GET /api/v1/admin/yearly-calendars/`
- `POST /api/v1/admin/yearly-calendars/`
- `GET /api/v1/admin/yearly-calendars/{yearlyCalendarId}/`
- `PATCH /api/v1/admin/yearly-calendars/{yearlyCalendarId}/`
- `DELETE /api/v1/admin/yearly-calendars/{yearlyCalendarId}/`

Request fields:
- `calendar_year`
- `calendar_name`
- `status_code`

### Calendar Special Days

- `GET /api/v1/admin/calendar-special-days/`
- `POST /api/v1/admin/calendar-special-days/`
- `GET /api/v1/admin/calendar-special-days/{specialDayId}/`
- `PATCH /api/v1/admin/calendar-special-days/{specialDayId}/`
- `DELETE /api/v1/admin/calendar-special-days/{specialDayId}/`

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
- `DELETE /api/v1/admin/general-charge-codes/{generalChargeCodeId}/`

Request fields:
- `business_unit_id`
- `code`
- `name`
- `charge_type_code`
- `cost_center_id`
- `approver_keys`
- `billable_flag`
- `requires_approval_flag`
- `description_required_flag`
- `valid_from`
- `valid_to`
- `status_code`

Response notes:
- the returned General Charge Code payload includes `routing_health`
- ad-hoc approver-role entries include `status`, `active_member_count`, and
  `has_active_members`

### General Charge Code Approval Roles

- `GET /api/v1/admin/general-charge-code-approval-roles/`
- `POST /api/v1/admin/general-charge-code-approval-roles/`
- `GET /api/v1/admin/general-charge-code-approval-roles/{approvalRoleId}/`
- `PATCH /api/v1/admin/general-charge-code-approval-roles/{approvalRoleId}/`
- `DELETE /api/v1/admin/general-charge-code-approval-roles/{approvalRoleId}/`

Request fields:
- `role_code`
- `name`
- `description`
- `member_employee_ids`
- `status_code`

Response notes:
- the returned payload includes `active_member_count`, `has_active_members`,
  `dependent_general_charge_code_count`, `dependent_general_charge_codes`, and
  `routing_health`

### Projects

- `GET /api/v1/admin/projects/`
- `POST /api/v1/admin/projects/`
- `GET /api/v1/admin/projects/{projectId}/`
- `PATCH /api/v1/admin/projects/{projectId}/`
- `DELETE /api/v1/admin/projects/{projectId}/`

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
- `DELETE /api/v1/admin/project-assignments/{assignmentId}/`

### Calendar Period Rules

- `GET /api/v1/admin/calendar-period-rules/`
- `POST /api/v1/admin/calendar-period-rules/`
- `GET /api/v1/admin/calendar-period-rules/{periodRuleId}/`
- `PATCH /api/v1/admin/calendar-period-rules/{periodRuleId}/`
- `DELETE /api/v1/admin/calendar-period-rules/{periodRuleId}/`
- `business_unit_id` is required on create and update payloads
- `working_on_saturdays_flag` and `working_on_sundays_flag` are supported on create and update payloads
- `saturday_max_hours` and `sunday_max_hours` are supported on create and update payloads

## 6. Collection Filtering

Supported on lifecycle-managed admin collections:
- query parameter: `status`
- if omitted, return all rows visible in scope
- if provided, filter by the entity status code

Applied collections include:
- countries
- offices
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
- `POST /api/v1/timesheets/`
- `GET /api/v1/timesheets/{timesheetId}/`
- `PUT /api/v1/timesheets/{timesheetId}/lines/`
- `POST /api/v1/timesheets/{timesheetId}/submit/`
- `POST /api/v1/timesheets/{timesheetId}/withdraw/`

Create payload:
- `week_start_date`: required Monday date
- `copy_previous_week`: optional boolean-like flag

Create behavior:
- normal create still opens an empty weekly timesheet in `CREATED` status
- when `copy_previous_week` is truthy and Office configuration enables the
  feature, the system copies from the employee's most recent approved earlier
  timesheet
- copied lines are shifted by weekday into the target week and still pass the
  normal target-week validations
- if the Office flag is disabled, the create call fails with
  `TIMESHEET_COPY_PREVIOUS_WEEK_DISABLED`
- if no approved earlier source exists, the create call fails with
  `TIMESHEET_COPY_PREVIOUS_WEEK_SOURCE_NOT_FOUND`

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

Approval endpoint behavior:
- `TS_ADMIN` can use the `GET` approval endpoints for scoped oversight
  visibility only
- `POST approve` and `POST reject` remain limited to actual routed approvers or
  matching General Charge Code approval-role holders
- no admin override approval endpoint is introduced in the current version

## 9. Report Export Endpoints

HTML report export routes:
- `GET /reports/project-time/export/`
- `GET /reports/pending-approvals/export/`
- `GET /reports/missing-timesheets/export/`
- `GET /reports/archived-timesheets/export/`
- `GET /reports/audit-history/export/`
- `GET /reports/integration-jobs/export/`
- `GET /reports/employee-utilization/export/`
- `GET /reports/office-bu-time-summary/export/`
- `GET /reports/general-charge-code-usage/export/`
- `GET /reports/approval-turnaround/export/`

Report export notes:
- Project Time HTML results may be grouped and collapsible in the browser UI
  without changing the CSV export contract
- Project Time CSV export remains a flat detail export using the active filters
  and the same server-side scope rules

Current `/api/v1` export support remains narrower than the HTML UI and is only
implemented for Missing Timesheets by Project.

### Missing Timesheets By Project

- `POST /api/v1/reports/missing-timesheets/exports/`
- `GET /api/v1/reports/missing-timesheets/export.csv`

POST payload:
- `project_ids`: optional array of project ids

POST behavior:
- validates role and project scope
- returns a JSON payload with report metadata and `export_uri`

GET behavior:
- downloads a CSV attachment using query-string project filters
- enforces the same project scope as the HTML report
- CSV rows include project name, employee name, employee email, and missing week start date

## 10. Current Authorization Expectations

- `TS_ADMIN_MASTER` can call the Country and Office admin JSON endpoints
- `TS_ADMIN` can call the implemented admin master-data endpoints inside active Office and Business Unit scope
- `TS_ADMIN` can use approval `GET` endpoints for scoped oversight and can use
  admin timesheet action endpoints for exception handling
- `TS_ADMIN` can use the advanced admin reports only inside active Office and
  Business Unit scope, with the same scope enforcement applied to HTML CSV
  exports
- `PROJECT_MANAGER` is the approval-workflow API role
- `PROJECT_OWNER`, `PROJECT_MANAGER`, and `TS_ADMIN` can use the project missing-timesheets export API inside their project scope
- `PROJECT_OWNER` and `PROJECT_MANAGER` gain reporting and inquiry access through the UI/report layer

## 11. Stable Error Code Highlights

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

### Reports

- `REPORT_INVALID_REQUEST`
- `REPORT_INVALID_SCOPE`

### Country And Office Administration

- `COUNTRY_CODE_REQUIRED`
- `COUNTRY_NAME_REQUIRED`
- `COUNTRY_NOT_UNIQUE`
- `COUNTRY_NOT_FOUND`
- `COUNTRY_DELETE_BLOCKED`
- `BUSINESS_UNIT_DELETE_BLOCKED`
- `CLIENT_DELETE_BLOCKED`
- `INTERNAL_CATEGORY_DELETE_BLOCKED`
- `COST_CENTER_DELETE_BLOCKED`
- `PRICING_MODEL_DELETE_BLOCKED`
- `YEARLY_CALENDAR_DELETE_BLOCKED`
- `CALENDAR_SPECIAL_DAY_DELETE_BLOCKED`
- `CALENDAR_PERIOD_RULE_DELETE_BLOCKED`
- `GENERAL_CHARGE_CODE_DELETE_BLOCKED`
- `GENERAL_CHARGE_CODE_APPROVAL_ROLE_DELETE_BLOCKED`
- `PROJECT_DELETE_BLOCKED`
- `PROJECT_ASSIGNMENT_DELETE_BLOCKED`
- `COUNTRY_REQUIRED`
- `COUNTRY_NAME_NOT_UNIQUE`
- `OFFICE_APPROVAL_MODE_REQUIRED`
- `OFFICE_ARCHIVE_YEARS_REQUIRED`
- `OFFICE_ARCHIVE_YEARS_INVALID`
- `OFFICE_CUTOFF_DATE_INVALID`

### General Charge Codes

- `GENERAL_CHARGE_CODE_COST_CENTER_REQUIRED`
- `GENERAL_CHARGE_CODE_COST_CENTER_OFFICE_MISMATCH`
- `GENERAL_CHARGE_CODE_APPROVER_ROLE_UNMANNED`
- `GENERAL_CHARGE_CODE_APPROVER_ROLE_INACTIVE`

### General Charge Code Approval Roles

- `GENERAL_CHARGE_CODE_APPROVAL_ROLE_INACTIVE_BLOCKED`
- `GENERAL_CHARGE_CODE_APPROVAL_ROLE_MEMBERS_REQUIRED`

### Calendar Special Days

- `CALENDAR_SPECIAL_DAY_CALENDAR_REQUIRED`
- `CALENDAR_SPECIAL_DAY_CALENDAR_IMMUTABLE`
- `CALENDAR_SPECIAL_DAY_DATE_REQUIRED`
- `CALENDAR_SPECIAL_DAY_YEAR_MISMATCH`
- `CALENDAR_SPECIAL_DAY_NOT_UNIQUE`
- `CALENDAR_SPECIAL_DAY_GENERAL_CHARGE_CODE_OFFICE_MISMATCH`

## 11. Explicit Non-Endpoints

The following actions currently exist in the server-rendered UI but are not documented here as JSON endpoints:
- guarded delete actions for Business Units, Employees, Yearly Calendars, Calendar Special Days, Clients, Internal Categories, Cost Centers, and Pricing Models
