# 2026-05-17 Basic User Shell Reduction

## Goal

Reduce the authenticated shell for employees who hold only the basic `USER`
role so they see only the useful personal screens.

## Scope

- remove `Dashboard` from `My info` for basic users
- redirect `/` to `/ts/` for basic users instead of rendering the dashboard
- remove `Reports` from the left navigation for basic users
- remove the entire `TS/Project Management` group when it becomes empty
- deny direct access to the reports hub for basic users

## Interpretation

- “users with USER role” is implemented as employees who hold only the basic
  `USER` role and no additional operational or admin roles
- users who also hold `PROJECT_OWNER`, `PROJECT_MANAGER`, `TS_ADMIN`, or
  `TS_ADMIN_MASTER` keep the broader shell
