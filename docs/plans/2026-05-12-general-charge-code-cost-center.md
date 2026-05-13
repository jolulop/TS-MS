# General Charge Code Cost Center Requirement

## 1. Goal

Replace the unused `Common Code` attribute on General Charge Codes with a mandatory Cost Center assignment from the active Office.

## 2. Scope

In scope:
- General Charge Code schema change
- System Management General Charge Code create and edit UI
- General Charge Code admin API and service validation
- developer seed data and test helpers
- tests and current markdown docs affected by the change

Out of scope:
- other System Management screens
- changes to project rules beyond keeping existing references consistent

## 3. Source Documents

- `docs/functional-spec-v5.4.md`
- `docs/ui-screen-spec-v5.4.md`
- `docs/integration-api-spec-v5.4.md`
- `docs/business-rules-catalog-v5.4.md`
- `docs/data-model-erd-v5.4.md`
- `AGENTS.md`

## 4. Affected Areas

- `apps/master_data/models.py`
- `apps/master_data/services.py`
- `apps/core/system_views.py`
- `apps/master_data/management/commands/seed_dev_data.py`
- `tests/helpers.py`
- `tests/test_general_charge_code_admin.py`
- `tests/test_system_management_ui.py`
- docs and schema notes

## 5. Data Model Changes

- remove `general_charge_code.common_code_flag`
- add mandatory `general_charge_code.cost_center_id`
- enforce that the selected Cost Center belongs to the same active Office as the General Charge Code
- backfill existing General Charge Codes during migration using an Office Cost Center where possible, and fail fast if an Office has no Cost Center available for backfill

## 6. Service and UI Changes

- remove `Common Code` from API payloads and HTML forms
- require `cost_center_id` on create and update
- show Cost Center in serialized payloads and detail views
- populate the Cost Center dropdown from the active Office

## 7. Tests

- admin API create and update require a Cost Center
- Office mismatch for Cost Center is rejected
- HTML create and edit require a Cost Center
- legacy `common_code_flag` expectations are removed

## 8. Risks

- migration backfill depends on at least one Office-level Cost Center existing for each Office that already has General Charge Codes
- downstream code that assumed `common_code_flag` exists must be updated everywhere in the repo
