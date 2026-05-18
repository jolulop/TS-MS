# Functional Specification v5.2

Superseded by [functional-spec-v5.7.md](/home/jolulop/code/TS-MS/docs/functional-spec-v5.7.md).

Historical note only. Do not use this file as the current implementation source of truth.

## Purpose

This v5.2 note records the Milestone 2 correction pass requested after the first System Management UI rollout.

It originally targeted the legacy v5.1 functional-specification document set and is preserved here only as a historical delta.

## Lifecycle And Delete Clarification

Insert into the master-data lifecycle rules:

- System Management records covered by v5.2 do not use delete in the UI.
- Administrative removal from day-to-day use is handled by status changes, typically `ACTIVE -> INACTIVE`.
- Update flows must be available from the detail page for all supported System Management screens.

## System Management Collection Behavior

Insert into the shared System Management list behavior:

- Every lifecycle-managed collection must provide a status filter.
- The filter must at least support `Active` and `Inactive` where the entity uses those lifecycle states.
- The collection must expose an explicit `Open / Edit` action for each row.

## New Functional Coverage In v5.2

Insert into the Milestone 2 or System Management coverage section:

- Projects are now part of the Milestone 2 System Management UI scope.
- Project Assignments are now part of the Milestone 2 System Management UI scope.
- Calendar Period Rules are now part of the Milestone 2 System Management UI scope.

## Project Rules Insertions

Insert into the project setup rules:

- Project setup UI must enforce that:
  - project owner holds `PROJECT_OWNER`
  - project manager holds `PROJECT_MANAGER`
  - client belongs to the same Office as the project
  - cost center belongs to the same Office as the project
  - pricing model belongs to the same Office as the project
  - internal category belongs to the same Business Unit as the project
  - pricing model is mandatory
- Project setup remains Business Unit scoped for `TS_ADMIN`.

## Project Assignment Rules Insertions

Insert into the project assignment rules:

- Assignment UI must prevent creation for closed projects.
- Assignment UI must only allow employees who are active and in the project Business Unit scope.
- Assignment dates must remain within the allowed project date window.

## Calendar Period Rule Insertions

Insert into the calendar rules section:

- Calendar Period Rules are manageable through System Management in v5.2.
- The UI and backend must enforce:
  - `effective_to >= effective_from`
  - no overlapping period rules in the same yearly calendar

## Documentation Cross-Reference

Use these v5.2 notes together with:
- `docs/ui-screen-spec-v5.2.md`
- `docs/integration-api-spec-v5.2.md`
