# 2026-05-17 Project Manager Project Assignment System Access

## Goal

Allow `PROJECT_MANAGER` users to use `System Management > Project Assignments`
for the projects they manage.

## Scope

- `PROJECT_MANAGER` can open `System Management`
- `PROJECT_MANAGER` can open `System Management > Project Assignments`
- `PROJECT_MANAGER` can list assignments for managed projects only
- `PROJECT_MANAGER` can create, update, and delete assignments for managed
  projects only

## Key Rules

- `PROJECT_MANAGER` does not gain access to `System Management > Projects`
- access remains limited to:
  - active Office
  - current Business Unit scope
  - projects where `project_manager_employee_id == current_user.employee_id`
- out-of-scope assignments remain blocked server-side
