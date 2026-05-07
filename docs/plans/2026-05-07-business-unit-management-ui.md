# Business Unit Management UI

## 1. Goal

Add Business Unit management to System Management so TS Admin users can list and maintain Business Units already inside their assigned scope, including BU-level configuration.

## 2. Scope

In scope:
- add a Business Units section under System Management
- add a scoped Business Unit list screen
- add a Business Unit create flow in System Management
- add a Business Unit detail/configuration screen
- add backend management service methods and matching admin JSON endpoints
- add UI and API tests

Out of scope:
- reminder-rule management
- audit history tabs in the UI
- changing Business Unit country

## 3. Source documents

- `docs/TS MAnagement functional specification v.5.3.docx`
- `docs/UI - Screen Specification  v5.3.docx`
- `AGENTS.md`

## 4. Current state

- Business Units exist in the data model and session scope.
- There is no System Management section, view, or admin service for Business Units.
- Existing System Management screens follow a shared list/detail shell with server-side scope enforcement.

## 5. Target behavior

- TS Admin can open `/system/business-units/` and see only Business Units in current admin scope and active office.
- TS Admin can create a new Business Unit in the active office.
- The creating TS Admin is added to the new Business Unit scope so the record is immediately manageable after the redirect.
- TS Admin can open a Business Unit detail screen and update:
  - BU code
  - name
  - description
  - lifecycle status
  - BU configuration values
- Office remains read-only and immutable.
- New Business Units start with default configuration values that can be refined on the detail screen.

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/core`

Frontend screens/features:
- System Management overview
- System Management sub-navigation
- Business Unit list/detail screens

APIs:
- admin Business Unit list/detail endpoints

## 7. Tests

- admin API scope and update coverage
- System Management UI coverage for Business Unit visibility and update flows

## 8. Risks and assumptions

- The current codebase already uses `SCR-100` and `SCR-101` for Country Management, while the v5.3 UI document uses those identifiers for Business Unit list/detail. This slice will avoid renumbering the existing office screens and use unique Business Unit screen labels in code.
- Assumption: creating a Business Unit also adds the creating TS Admin employee to that BU scope, because otherwise the newly created BU would fall outside the session-derived scoped BU set and be unusable immediately after creation.
