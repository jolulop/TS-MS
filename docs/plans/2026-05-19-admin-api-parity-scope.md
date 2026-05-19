# Admin API Parity Scope Proposal

## Status

- completed
- date: `2026-05-19`

## Goal

Define the concrete `/api/v1` scope needed to bring Office and Country administration to parity with the current System Management UI, including guarded delete behavior.

This document began as a design proposal and now reflects the implemented v1 scope for Country and Office JSON admin parity.

## Why This Work Exists

The current JSON API already exposes scoped CRUD for most admin master data:

- Business Units
- Employees
- Clients
- Internal Categories
- Cost Centers
- Pricing Models
- Yearly Calendars
- Calendar Special Days
- General Charge Codes
- Projects
- Project Assignments
- Calendar Period Rules

But two important UI-managed areas still have no `/api/v1` parity:

- Countries
- Offices

In addition, several entities already support guarded delete behavior in the UI/service layer, but that behavior is not consistently available through JSON endpoints.

## Current Codebase Facts

### Existing service-layer capabilities

The repo already has reusable service logic for:

- `CountryManagementService`
  - `list_countries`
  - `get_country`
  - `create_country`
  - `update_country`
  - `delete_country`
- `OfficeManagementService`
  - `list_offices`
  - `get_office`
  - `create_office`
  - `update_office`
  - `delete_office`

Those flows already enforce:

- `TS_ADMIN_MASTER` authorization
- validation
- uniqueness rules
- audit logging
- guarded delete behavior

### Existing JSON API pattern

The implemented admin JSON API uses this structure:

- collection endpoints:
  - `GET /api/v1/admin/<resource>/`
  - `POST /api/v1/admin/<resource>/`
- detail endpoints:
  - `GET /api/v1/admin/<resource>/{id}/`
  - `PATCH /api/v1/admin/<resource>/{id}/`

Views are thin and call service-layer methods.

Errors use:

- `AuthError`
- `error_response(code, message, status)`

### Important domain note

`Country` is still a real model in the codebase and remains the parent of `Office`.

This proposal therefore covers both:

- `Country` master administration
- `Office` administration under a selected Country

## Proposed v1 Scope

### 1. Country admin endpoints

Add:

- `GET /api/v1/admin/countries/`
- `POST /api/v1/admin/countries/`
- `GET /api/v1/admin/countries/{countryId}/`
- `PATCH /api/v1/admin/countries/{countryId}/`
- `DELETE /api/v1/admin/countries/{countryId}/`

Authorization:

- `TS_ADMIN_MASTER` only

Collection filtering:

- support `?status=<STATUS_CODE>` like the existing lifecycle-managed admin collections

Request fields:

- `country_code`
- `country_name`
- `status_code`

Response envelope:

- collection: `{ "countries": [...] }`
- detail/create/update: `{ "country": { ... } }`
- delete success: `{ "deleted": true, "entity": "country", "id": <countryId> }`

Guarded delete behavior:

- no cascade deletion
- delete only when no protected references remain
- if blocked, return the current business error from the service layer

Expected blocked case:

- Country still referenced by one or more Offices

### 2. Office admin endpoints

Add:

- `GET /api/v1/admin/offices/`
- `POST /api/v1/admin/offices/`
- `GET /api/v1/admin/offices/{officeId}/`
- `PATCH /api/v1/admin/offices/{officeId}/`
- `DELETE /api/v1/admin/offices/{officeId}/`

Authorization:

- `TS_ADMIN_MASTER` only

Collection filtering:

- support `?status=<STATUS_CODE>`

Request fields for create:

- `country_id`
- `office_name`
- `status_code`

Office configuration payload fields:

- `approval_mode_code`
- `allow_employee_withdraw_flag`
- `timesheet_cutoff_date`
- `count_non_billable_in_daily_limit_flag`
- `archive_after_years`
- `enable_timer_flag`
- `enable_leave_integration_flag`
- `enable_copy_previous_week_flag`

Bootstrap create fields, matching the current UI flow:

- `bootstrap_bu_code`
- `bootstrap_bu_name`
- `bootstrap_bu_description`
- `bootstrap_admin_employee_code`
- `bootstrap_admin_full_name`
- `bootstrap_admin_email`

Request fields for update:

- `country_id`
- `office_name`
- `status_code`
- any Office configuration fields listed above

Response envelope:

- collection: `{ "offices": [...] }`
- detail/create/update: `{ "office": { ... } }`
- delete success: `{ "deleted": true, "entity": "office", "id": <officeId> }`

Guarded delete behavior:

- no cascade deletion
- keep the existing service behavior as source of truth
- if blocked, return a structured business error

Expected blocked cases:

- Office still referenced by Business Units
- Office still referenced by other protected records

## Guarded Delete API Rules

This proposal intentionally keeps delete behavior simple and aligned with the UI:

- use real `DELETE` endpoints
- do not perform destructive cascade cleanup
- if protected dependencies exist, reject deletion
- use structured JSON error responses
- audit both successful and blocked delete attempts where the service flow already does so or where implementation adds it

Recommended blocked-delete response pattern:

```json
{
  "error": {
    "code": "OFFICE_DELETE_BLOCKED",
    "message": "Office cannot be deleted because it is still referenced by Business Units or other records."
  }
}
```

Recommended HTTP status for guarded-delete failures:

- `400`

Rationale:

- this matches the current business-validation style used by the repo
- the operation is syntactically valid but business-blocked

## Serialization Expectations

### Country

The API should reuse the existing service serialization, including:

- `id`
- `country_code`
- `country_name`
- `status_code`
- `status_label`
- `office_count`
- audit timestamps where already exposed by service serializers

### Office

The API should reuse the existing service serialization, including:

- `id`
- `country_id`
- `country_code`
- `country_name`
- `office_name`
- `status_code`
- `status_label`
- `active_employee_count`
- inherited Office configuration fields
- bootstrap / current administrator summary if already exposed in `get_office`

## Error-Code Expectations

The new endpoints should preserve current stable service error codes rather than inventing new ones unless necessary.

Examples already present in service logic:

- `COUNTRY_NOT_FOUND`
- `COUNTRY_CODE_REQUIRED`
- `COUNTRY_NAME_REQUIRED`
- `COUNTRY_NOT_UNIQUE`
- `COUNTRY_DELETE_BLOCKED`
- `COUNTRY_REQUIRED`
- `COUNTRY_NAME_NOT_UNIQUE`

Implementation follow-up:

- review naming consistency for Office-specific errors
- some current Office service errors still reuse `COUNTRY_*` prefixes
- keep v1 behavior compatible, but consider a later normalization pass if the business wants clearer Office-specific API codes

## Audit Requirements

The API endpoints must reuse the same audit model as the UI/service flows:

- create
- update
- delete
- blocked delete where implemented or extended

At minimum, the API channel must not bypass existing audit behavior.

## Out of Scope For This v1 Proposal

Not included in the first implementation scope:

- bulk Country or Office operations
- Office admin JSON endpoints for nested bootstrap edits after creation
- JSON parity for every existing guarded delete in the system
- enterprise-wide `TS_ADMIN_MASTER` reporting APIs
- export parity work outside existing report export scope
- API redesign or version bump

## Recommended Implementation Sequence

### Phase 1

- add Country collection/detail/delete JSON endpoints
- add Office collection/detail/delete JSON endpoints
- wire them in `apps/master_data/views.py` and the matching API URL config
- reuse the existing service-layer methods unchanged where possible

### Phase 2

- document the new endpoints in `docs/integration-api-spec-v5.8.md` or the next promoted version
- add JSON API tests for:
  - list
  - create
  - detail
  - update
  - allowed delete
  - blocked delete
  - auth denial

### Phase 3

- evaluate whether more existing guarded delete flows should receive JSON parity:
  - Business Units
  - Employees
  - Yearly Calendars
  - Calendar Special Days
  - Clients
  - Internal Categories
  - Cost Centers
  - Pricing Models

## Acceptance View For This Proposal

This scope is ready to implement when the team agrees on:

- `TS_ADMIN_MASTER` as the only role for these endpoints
- reusing current service-layer rules and audit behavior
- `DELETE` as the verb for guarded deletes
- no cascade deletion
- Office create JSON including bootstrap BU + bootstrap admin fields

## Summary

This proposal keeps the work intentionally narrow:

- add missing Country admin JSON parity
- add missing Office admin JSON parity
- expose existing guarded delete behavior through structured JSON responses
- do not change business rules
- do not duplicate UI logic in controllers
