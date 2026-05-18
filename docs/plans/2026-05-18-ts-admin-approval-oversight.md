# TS Admin Approval Oversight

## 1. Goal

Add a `TS_ADMIN` approval-oversight workspace that exposes pending approval visibility and exception-handling entry points without granting admin approve/reject authority in place of the routed Project Manager or matching General Charge Code approver.

## 2. Scope

In scope:
- `TS_ADMIN` access to a scoped approval oversight workspace
- pending approval visibility across scoped Business Units
- aging and stalled approval visibility
- filter and search controls for oversight
- links to related timesheet, project, and approval detail
- related timesheet exception actions in HTML UI:
  - reopen approved timesheets
  - admin-withdraw approved timesheets back to submitted
  - archive eligible approved timesheets
  - restore archived timesheets
- current docs and tests affected by the change

Out of scope:
- admin approve/reject of approval items
- bulk approval/rejection
- approval reassignment or escalation workflow
- new schema changes

## 3. Source Documents

- `docs/functional-spec-v5.6.md`
- `docs/ui-screen-spec-v5.6.md`
- `docs/authorization-matrix-v5.6.md`
- `docs/integration-api-spec-v5.6.md`
- `AGENTS.md`

## 4. Affected Areas

- `apps/auth/policies.py`
- `apps/timesheets/services.py`
- `apps/core/approval_views.py`
- `apps/core/ts_views.py`
- approval and timesheet templates
- approval and timesheet UI tests
- current v5.6 docs

## 5. Functional Design

- reuse `/approvals/` as the approval workspace
- when the current user is `TS_ADMIN`, render an oversight-oriented pending queue instead of an approver-centric queue
- keep approval decision authority unchanged:
  - Project Managers approve/reject project approval items assigned to them
  - matching General Charge Code approvers approve/reject routed GCC items
  - `TS_ADMIN` oversight is read-only for approval decisions unless the same employee independently matches an approver role
- expose timesheet exception actions from the related timesheet detail page rather than creating approval-item lifecycle actions

## 6. Rules

- all approval visibility must remain constrained to active Office plus scoped Business Units
- admin visibility does not imply approval authority
- stalled approvals are identified in the oversight UI only; no lifecycle state changes are introduced
- related timesheet exception actions must reuse existing service-layer authorization and audit behavior

## 7. Tests

- `TS_ADMIN` can open the approval workspace and see scoped pending items
- approval detail is visible to `TS_ADMIN` in scope and remains read-only when admin is not an actual approver
- related links to project and timesheet are present
- HTML timesheet detail supports admin exception actions for authorized `TS_ADMIN`

## 8. Risks

- avoid accidentally widening admin approval authority while expanding visibility
- keep project-owner and project-manager approval flows unchanged
- ensure the shared approval route still behaves correctly for non-admin approvers
