# General Charge Code And Project Delete Actions

## 1. Goal

Extend System Management guarded delete support to `General Charge Codes` and `Projects`.

## 2. Scope

In scope:
- add delete actions to the General Charge Code and Project detail screens
- add guarded delete service methods for both entities
- preserve server-side scope checks and audit logging
- block deletion when protected references still exist

Out of scope:
- schema changes
- cascade-delete of timesheets, approvals, assignments, or other business data

## 3. Target Behavior

- unused General Charge Codes can be deleted from System Management
- used General Charge Codes are blocked when timesheets, approvals, or other protected records still reference them
- unused Projects can be deleted from System Management
- used Projects are blocked when project assignments, timesheets, approvals, or other protected records still reference them

## 4. Verification

- General Charge Code UI delete succeeds for an unused code
- General Charge Code UI delete is blocked when dependent records still exist
- Project UI delete succeeds for an unused project
- Project UI delete is blocked when dependent records still exist
