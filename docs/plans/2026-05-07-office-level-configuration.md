# Office-Level Configuration

## 1. Goal

Move operational timesheet configuration from `BusinessUnitConfiguration` to an inherited `OfficeConfiguration` so Office becomes the single source of truth and Business Units read configuration from their parent Office at runtime.

## 2. Scope

In scope:
- add Office-level configuration persistence
- migrate existing Business Unit configuration data to Office where safe
- remove Business Unit-owned configuration persistence and editing
- update runtime configuration reads in timesheet services
- update Office create/detail UI to own the configuration fields
- update Business Unit detail UI/API to show inherited Office configuration as read-only
- update seeds, schema docs, and tests

Out of scope:
- changing approval/calculation business rules themselves
- broadening Office management authorization from `TS_ADMIN_MASTER`
- reminder-rule or custom-attribute redesign

## 3. Source documents

- 2026-05-07 user change request in this task
- `AGENTS.md`
- `PLANS.md`
- existing Office and Business Unit management implementation

## 4. Current state

- `BusinessUnitConfiguration` stores approval mode, withdraw flag, cutoff date, daily-limit flag, retention, and reserved feature toggles.
- Timesheet runtime behavior reads those settings from Business Unit scope.
- Office management only handles Office identity and lifecycle status.
- Business Unit management owns editable configuration in both the UI and admin API.

## 5. Target behavior

- `OfficeConfiguration` becomes the single persisted source of truth for these settings:
  - approval mode
  - allow employee withdraw
  - timesheet cutoff date
  - count non-billable in daily limit
  - archive after years
  - enable timer
  - enable leave integration
  - enable copy previous week
- Office create/detail UI includes those settings and saves them with Office records.
- Business Unit create no longer creates its own configuration row.
- Business Unit detail and API still expose configuration, but the values are inherited from the parent Office and are not editable there.
- Timesheet runtime logic loads configuration from the Business Unit's parent Office with unchanged rule semantics.

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/timesheets`
- `apps/core`

Supporting artifacts:
- migrations
- seed/dev data
- schema diagram
- tests

## 7. Schema changes

- add `OfficeConfiguration` one-to-one with `Office`
- backfill Office configuration from existing Business Unit configuration values
- remove `BusinessUnitConfiguration`

## 8. API changes

- Business Unit admin payloads continue returning `configuration`, but it is inherited/read-only
- Business Unit create/update no longer accept configuration edits
- existing Office UI-backed service methods accept and persist configuration fields
- no new Office JSON API is added in this slice because none exists today

## 9. Tests

- Office UI tests for create/update with configuration
- Business Unit UI/API tests for inherited read-only configuration
- timesheet engine tests for inherited runtime cutoff/retention/approval behavior
- seed and helper updates for Office-level configuration

## 10. Risks and assumptions

- Assumption: keeping Office management authorization at `TS_ADMIN_MASTER` is the safer narrower behavior because the change request does not explicitly approve broader Office write access for `TS_ADMIN`.
- Risk: existing data may contain conflicting Business Unit configuration values within the same Office. The migration will fail fast in that case rather than silently choosing one.
- Confirmation requested by the user: after this change, no additional Business Unit business rules should change beyond loading inherited configuration from the parent Office at runtime. This implementation will follow that constraint.

## 11. Implementation status

Status:
- completed

Delivered:
- `OfficeConfiguration` as the only persisted source of truth for inherited operational settings
- forward migration from Business Unit configuration with conflict detection per Office
- Business Unit runtime serialization and timesheet services now reading configuration from the parent Office
- Office create/detail UI now owning configuration fields
- Business Unit detail UI now showing inherited configuration as read-only
- seed/dev data, schema documentation, and regression tests updated
