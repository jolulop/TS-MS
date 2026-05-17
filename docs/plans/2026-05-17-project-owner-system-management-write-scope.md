# 2026-05-17 Project Owner System Management Write Scope

## Goal

Allow `PROJECT_OWNER` users to use selected System Management screens for their
own projects:

- `System Management > Projects`
- `System Management > Project Assignments`

## Scope

- `PROJECT_OWNER` can list owned projects in System Management
- `PROJECT_OWNER` can create projects
- created projects are always owned by the current `PROJECT_OWNER`
- `PROJECT_OWNER` can update and delete owned projects only
- `PROJECT_OWNER` can list assignments for owned projects only
- `PROJECT_OWNER` can create, update, and delete assignments for owned projects only

## Key Rules

- `TS_ADMIN` keeps the broader Business Unit scoped behavior
- `PROJECT_OWNER` access is always limited to:
  - current Office
  - current Business Unit scope
  - projects where `project_owner_employee_id == current_user.employee_id`
- project ownership is enforced server-side during create and update for
  `PROJECT_OWNER`
- project manager selection still requires the selected employee to hold the
  `PROJECT_MANAGER` role under the existing business rule

## UI Notes

- In project create/edit for `PROJECT_OWNER`, the `Project Owner` field shows
  only the current user as the selected option
- `PROJECT_OWNER` gains `Projects` and `Project Assignments` entries in the
  System Management section navigation
