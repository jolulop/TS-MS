# Phase IV Timesheet Engine

## 1. Goal

Implement the first operational timesheet engine for the TS system in small, validated milestones. This phase will turn the existing timesheet and approval schema into working backend behavior for weekly timesheets, line validation, day limits, submission, approvals, and administrative lifecycle actions.

## 2. Scope

In scope:
- weekly Monday-Friday timesheet behavior
- timesheet line entry validation
- daily hour-limit validation from effective calendar rules
- submission lifecycle
- approval model and approval actions
- withdraw, reopen, and archive behavior
- audit coverage for sensitive timesheet and approval actions
- integration tests for key lifecycle and authorization paths

Out of scope:
- custom frontend screens for timesheet entry and approval
- reporting/export flows
- import/export integrations
- timer-based time capture
- leave conflict handling beyond what current schema directly supports

## 3. Source documents

- `docs/TS MAnagement functional specification v.5.1.docx`
- `docs/Use cases - Acceptance criteria v5..1.docx`
- `docs/Data Model - ERD v5.1.docx`
- `docs/Authorization Matrix aligned to Functional Specification v5.1.docx`
- `docs/Business Rules Catalog v5.1.docx`
- `AGENTS.md`
- `PLANS.md`

Note:
- The repository currently contains the approved spec documents as `.docx` files under `docs/`, not the markdown filenames referenced in `AGENTS.md`. This plan uses the current files present in the repo.

## 4. Current state

- The schema already includes `weekly_timesheet`, `timesheet_line`, `timesheet_submission_cycle`, `approval_item`, and `approval_action`.
- Employee auth/session and scoped TS Admin employee setup are implemented.
- Classification master data is implemented for clients, internal categories, cost centers, and general charge codes.
- Calendar, project, and project-assignment tables exist at the schema level but do not yet have dedicated management APIs.
- The `apps/timesheets` module currently has models only; there are no services, views, URLs, policies, or tests for timesheet behavior.

## 5. Target behavior

After Phase IV:
- users can create and update their own weekly timesheets
- users can add and edit timesheet lines only for valid Monday-Friday dates in the sheet week
- users can charge only to valid assigned projects or valid general charge codes for the work date
- daily hours cannot exceed the effective calendar period rule
- users can submit and withdraw timesheets according to status rules
- approvers can approve or reject relevant approval items
- reopened and archived states follow server-side lifecycle enforcement
- sensitive timesheet and approval actions are auditable

## 6. Affected areas

Backend modules:
- `apps/timesheets`
- `apps/auth`
- `apps/master_data`
- `apps/audit`
- `config`
- `tests`

Frontend screens/features:
- none in this phase by default

Database / migrations:
- maybe none for Milestone 1 if current schema is sufficient
- forward-only migrations only if implementation reveals missing lifecycle or approval constraints

APIs:
- add user timesheet endpoints under `/api/v1/`
- add approval/action endpoints under `/api/v1/`
- add admin reopen/archive endpoints under `/api/v1/`

Jobs / integrations:
- none in this phase

## 7. Business rules impacted

- one employee can have at most one weekly timesheet per week
- a timesheet week is Monday to Friday only
- weekend entry is not allowed
- employees can charge only to active assigned projects for the work date, or valid general charge codes for the work date
- daily hour limits come from the effective calendar period rule
- approved timesheets are locked
- archived timesheets are not editable
- denied-by-default authorization remains server-side
- submit, withdraw, reopen, approve, reject, and archive actions must remain auditable

## 8. Authorization impact

Roles affected:
- `USER`
- `TS_ADMIN`
- `PROJECT_OWNER`
- `PROJECT_MANAGER`

Scope affected:
- timesheet owner scope
- project manager/project owner approval scope
- TS Admin reopen/archive scope

Backend enforcement points:
- centralized timesheet policy helpers
- timesheet query scoping
- approval-item query scoping
- lifecycle transition services

## 9. Data model changes

- migration needed: maybe later, not assumed for Milestone 1
- tables affected:
  - `weekly_timesheet`
  - `timesheet_line`
  - `timesheet_submission_cycle`
  - `approval_item`
  - `approval_action`
  - `audit_log`
- reference data seed changes:
  - none expected initially because core lifecycle domains already exist
- backfill needed: no

## 10. API changes

Planned endpoint groups:
- user weekly timesheets
- user timesheet lines
- user submit/withdraw actions
- approver approval actions
- TS Admin reopen/archive actions

Milestone 1 planned endpoints:
- `GET /api/v1/timesheets/`
- `POST /api/v1/timesheets/`
- `GET /api/v1/timesheets/<id>/`
- `PUT /api/v1/timesheets/<id>/lines/`

## 11. UI changes

Screens to add/change:
- none in this phase unless later requested

## 12. Audit and logging impact

Audit events to add/update:
- timesheet submit
- timesheet withdraw
- timesheet reopen
- approval approve
- approval reject
- archive/restore if archive is implemented in this phase
- denied sensitive actions where policy requires it

## 13. Milestones

### Milestone 1
- weekly timesheet create/list/detail
- line save/replace behavior
- Monday-Friday validation
- charge-target validity checks
- daily hour-limit checks from effective calendar period rules

### Milestone 2
- submission lifecycle
- submission-cycle creation
- submit/withdraw status transitions
- audit coverage for submit/withdraw

### Milestone 3
- approval-item generation
- approve/reject actions
- approval action history
- PM/PO scoped approval access

### Milestone 4
- reopen and archive administrative lifecycle
- locked-state enforcement after approval/archive
- final audit coverage and regression pass

## 14. Test plan

Unit tests:
- week/date validation helpers
- calendar day-limit resolution
- charge-target validation helpers
- lifecycle transition guards
- approval routing helpers

Integration tests:
- user creates one weekly timesheet per week
- user cannot save weekend lines
- user cannot exceed daily limits
- user cannot charge to invalid/unassigned targets
- submit/withdraw transitions
- approval approve/reject transitions
- reopen/archive enforcement

## 15. Risks and mitigations

- Risk: implementing lifecycle and approvals before validation rules are stable.
  - Mitigation: build the engine in milestones, starting with save validation.
- Risk: calendar/project prerequisites are only schema-level today.
  - Mitigation: Milestone 1 will query existing tables directly and use tests/helpers to prove the behavior before adding admin UIs for those entities.
- Risk: broad authorization leaks unrelated lines to approvers.
  - Mitigation: add centralized timesheet and approval policy helpers before approval actions.

## 16. Rollout / deployment notes

- feature flag needed: no
- migration sequencing:
  - only if later milestones reveal missing constraints
- backward compatibility:
  - existing auth/admin/master-data APIs stay unchanged

## 17. Open questions / assumptions

- Assumption: Milestone 1 is API-only and does not add custom timesheet UI yet.
- Assumption: the existing calendar/project/project-assignment schema is sufficient to validate line entry without adding management APIs in the same milestone.
- Assumption: line save behavior will replace the sheet’s editable lines in one request to keep the first slice small and deterministic.
- Assumption: Milestone 3 implements project-scoped approval routing first. `APPROVAL_MODE=PROJECT` is supported, missing BU configuration defaults to `PROJECT`, and `LINE`/`MIXED` modes remain deferred.
- Assumption: non-required general charge-code lines are treated as already approved on submit, while general charge codes that require routed approval are blocked until approver configuration exists in a later slice.

## 18. Definition of done

- code implemented
- migrations added only if needed
- tests added/updated
- audit coverage added where required
- docs updated where required
- PLANS.md updated with current progress

## 19. Implementation status

Status:
- in progress

Completed milestone:
- Milestone 1: weekly timesheet create/list/detail and line validation engine
- Milestone 2: submission lifecycle with submit/withdraw transitions
- Milestone 3: project-scoped approval worklist and approval actions

Delivered in Milestone 1:
- user weekly timesheet create/list/detail APIs
- line replacement API for editable timesheets
- Monday-Friday week validation
- project assignment and general-charge-code target validation
- calendar-based daily hour-limit validation
- timesheet policy helpers for view/edit
- integration tests for timesheet creation, duplicate protection, line validation, and day limits

Delivered in Milestone 2:
- submit and withdraw APIs for employee-owned timesheets
- submission-cycle creation and completion behavior
- submit/withdraw audit coverage
- edit locking while timesheets are submitted
- integration tests for submit/withdraw transitions and empty-timesheet guards

Delivered in Milestone 3:
- submission now creates project-scoped approval items for project-charged time
- non-required general charge-code lines now receive approved line state during submission
- PM-scoped approval worklist/detail APIs
- PM approve/reject actions with immutable approval-action history
- timesheet finalization to `APPROVED` when all required project approvals complete
- timesheet transition to `REJECTED` when an approval item is rejected
- self-approval prevention during approval routing and action handling
- integration tests for approval creation, approve/reject transitions, worklist scope, self-approval blocking, and unsupported required general-code approval routing

Still pending:
- Milestone 4: reopen, withdraw, archive, and locked-state enforcement

Validation run for Milestones 1-3:
- `make format`
- `make lint`
- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py makemigrations --check`
- `.venv/bin/python manage.py migrate`
- `make test`
- `make format-check`
