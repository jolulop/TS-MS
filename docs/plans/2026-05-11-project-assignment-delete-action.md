# Project Assignment Delete Action

## 1. Goal

Add a `Delete Project Assignment` action to System Management so transient assignment records can be removed from the Project Assignment detail screen.

## 2. Scope

In scope:
- add a delete action to the Project Assignment detail screen
- add a service delete method with scope checks and audit logging
- redirect back to the Project Assignment collection after successful delete

Out of scope:
- schema changes
- cascade-delete of projects, employees, timesheets, or other business data

## 3. Target Behavior

- `TS_ADMIN` can delete an in-scope Project Assignment from its detail screen
- deletion is audited
- if protected references are introduced or already exist, deletion is blocked with a clear message

## 4. Verification

- Project Assignment UI delete succeeds for an existing in-scope assignment
