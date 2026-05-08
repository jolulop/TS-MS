# Client Delete Action

## 1. Goal

Add a `Delete Client` action to System Management so `TS_ADMIN` users can remove unused Clients from the Client detail screen.

## 2. Scope

In scope:
- add a delete button to the Client detail screen
- add a guarded Client delete service
- block deletion when referential integrity dependencies exist
- add UI regression tests for successful and blocked delete cases

Out of scope:
- JSON API delete endpoint
- cascading cleanup of dependent records
- schema changes

## 3. Source documents

- 2026-05-08 user request in this task
- `AGENTS.md`
- `PLANS.md`
- existing Office, Employee, and Business Unit delete patterns

## 4. Target behavior

- Client detail shows a `Delete Client` action
- deleting an unused Client succeeds and redirects back to the Client list
- deleting a Client referenced by a child Client, Project, or other protected record is blocked with a clear message

## 5. Implementation status

Status:
- completed

Delivered:
- Client detail now includes a guarded `Delete Client` action
- Client deletion now succeeds only when Django referential integrity allows it
- deletion is blocked cleanly when child Clients, Projects, or other protected records still reference the Client
- UI regression coverage now proves both successful and blocked delete cases
