# Admin API Delete Parity Wave

## Goal

Extend the existing `/api/v1/admin` master-data endpoints with guarded `DELETE`
support wherever the underlying service layer already supports safe deletion.

## Scope

- add guarded `DELETE` to the existing admin JSON detail endpoints for:
  - Business Units
  - Clients
  - Internal Categories
  - Cost Centers
  - Pricing Models
  - Yearly Calendars
  - Calendar Special Days
  - Calendar Period Rules
  - General Charge Codes
  - General Charge Code Approval Roles
  - Projects
  - Project Assignments
- reuse service-layer validation and delete rules
- audit blocked delete attempts through the API channel
- add focused API regression tests

## Out Of Scope

- employee list/detail/delete API parity
- employee transfer API
- new business rules for deletion

## Verification

- focused admin API tests
- Django system check
- Ruff on touched files

## Status

- completed
