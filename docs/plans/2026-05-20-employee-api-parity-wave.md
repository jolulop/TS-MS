# Employee API Parity Wave

## Goal

Complete the existing `/api/v1/admin/employees/` JSON surface so Employee
administration has the same core list/detail/delete parity already available in
the HTML System Management flow.

## Scope

- add `GET /api/v1/admin/employees/`
- add `GET /api/v1/admin/employees/{id}/`
- add guarded `DELETE /api/v1/admin/employees/{id}/`
- keep the existing employee create, update, role-replace, and business-unit
  replace endpoints unchanged
- reuse the current service-layer authorization, serialization, and guarded
  delete rules
- audit blocked delete attempts through the API path
- add focused employee admin API regression coverage

## Out Of Scope

- employee transfer API
- new employee business rules
- changes to the existing employee create/update payload contract

## Verification

- focused employee admin API tests
- Django system check
- Ruff on touched files

## Status

- completed
