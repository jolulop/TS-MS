# General Charge Code Routing Governance

## Status

- completed
- date: `2026-05-19`

## Goal

Improve General Charge Code approval-role administration without changing the approval workflow model itself.

The current system already supports:

- built-in TS roles as GCC approvers
- Office-scoped ad-hoc GCC approval roles
- member assignments for ad-hoc roles
- GCC-level approver-role selection

The missing value is governance visibility and protection against broken ad-hoc routing setups.

## Implemented Scope

### 1. Richer ad-hoc approval-role visibility

Enhance ad-hoc approval-role serialization so admins can see:

- active member count
- whether the role currently has active members
- which General Charge Codes currently depend on the role
- dependent GCC count
- routing coverage status and warning text

### 2. Richer GCC routing visibility

Enhance General Charge Code serialization so admins can see:

- routing status
- whether selected ad-hoc roles are unmanned
- which selected ad-hoc roles are currently missing active members

### 3. Guardrails for referenced ad-hoc roles

Prevent admins from leaving a referenced ad-hoc role in a broken state:

- reject selecting an ad-hoc role with no active members on a GCC when `requires_approval_flag` is enabled
- reject updating a referenced ad-hoc role to `INACTIVE`
- reject removing all active members from a referenced ad-hoc role

This keeps governance strict for ad-hoc routes while preserving the existing built-in-role behavior.

### 4. UI and API exposure

Show the richer routing data in:

- System Management GCC list/detail
- System Management GCC Approval Role list/detail
- JSON admin API responses for GCCs and GCC approval roles

## Out Of Scope

- change the actual GCC approval decision model
- add bulk routing tools
- add escalation chains
- add new approval entities
- change built-in role semantics

## Verification Plan

- add service/API tests for unmanned ad-hoc role validation
- add UI tests for new routing/dependency visibility
- update v5.8 docs and acceptance references

## Verification Completed

- `.venv/bin/python manage.py check`
- `.venv/bin/pytest tests/test_general_charge_code_admin.py tests/test_system_management_ui.py -q`
- `git diff --check`
