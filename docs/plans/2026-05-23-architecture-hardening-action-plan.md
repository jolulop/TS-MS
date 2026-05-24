# Architecture Hardening Action Plan

## Purpose

Define the work plan to address architecture, authentication, write-path,
cache/state, security, and concurrency risks found in the senior architecture
review of the current v6.1 Django codebase.

This plan is intentionally implementation-oriented but does not change code by
itself. It should be used to split future work into small, reviewable PRs.

## Source Of Truth

- `docs/specification-index-v6.1.md`
- `docs/functional-spec-v6.1.md`
- `docs/authorization-matrix-v6.1.md`
- `docs/business-rules-catalog-v6.1.md`
- `docs/non-functional-requirements-v6.1.md`
- Current code on branch `Codex-5.5` at `e54ce9a`

## Current Findings

### Authentication

The current local login flow is a development adapter:

- HTML access entry posts `validated_email` through `apps.core.views.home`.
- JSON access entry posts `validated_email` through
  `apps.auth.views.initialize_session`.
- `apps.auth.services.SessionInitializationService` resolves the email to an
  internal `Employee`.
- `apps.auth.services.CurrentUserService` builds the internal role and Business
  Unit scope from TS data.
- `apps.auth.middleware.InternalSessionMiddleware` rebuilds `request.ts_user`
  from the database on every request.

This means the future Google SSO work should replace the external identity
adapter while keeping internal employee, role, and scope resolution.

### Write Paths

Durable writes are concentrated in:

- `apps.audit.services.write_audit_event`
- `apps.auth.services.SessionInitializationService`
- `apps.timesheets.services.TimesheetService`
- `apps.master_data.services`
- seed management commands under `apps/*/management/commands`

Most service-level write paths are already transactional. The major missing
piece is row locking or database-level exclusion for concurrent state changes
and overlapping validity windows.

### Cache And State

There is no shared application cache currently in use. State reuse is limited
to:

- Django session keys for employee id and validated email
- per-request `request.ts_user`
- transient object attributes such as `_configuration_cache` and
  `_administrators_cache` used during serialization

Role and Business Unit changes generally take effect on the next request
because `CurrentUser` is rebuilt in middleware.

### Primary Risks To Resolve

1. Production authentication adapter is not yet implemented.
2. Production settings are still development-default friendly.
3. One scoped report filter path can accept arbitrary Business Unit ids instead
   of intersecting with user scope.
4. Critical workflow transitions are transactional but not row-locked.
5. Overlap validations rely on service preflight checks without database-level
   protection.
6. Large service/view modules increase regression risk and slow future work.

## Work Plan

## Phase 0 - Baseline Guardrails

Goal: make the current findings reproducible and protect against accidental
scope regressions before larger refactors.

Tasks:

- Add focused tests for tampered scoped report filters:
  - `office-bu-time-summary`
  - `employee-utilization`
  - `general-charge-code-usage`
  - `approval-turnaround`
  - `archived-timesheets`
  - `audit-history`
  - `integration-jobs`
- Add tests confirming role and Business Unit changes take effect on the next
  request after middleware rebuild.
- Add tests for duplicate or stale session employee behavior when the employee
  is deactivated or loses all roles.

Likely files:

- `tests/test_reports_ui.py`
- `tests/test_auth_session.py`
- `tests/test_employee_authorization.py`
- `apps/core/reports_views.py`

Acceptance criteria:

- Out-of-scope filter ids never widen a report result.
- Stale sessions are cleared when the employee becomes invalid.
- Tests fail against the known scoped-filter issue before the fix and pass
  after implementation.

## Phase 1 - Scoped Report Hardening

Goal: eliminate report-scope widening by request parameters.

Tasks:

- Introduce small scope helper functions for single Business Unit filters:
  - parse selected Business Unit id
  - intersect it with `current_user.scoped_business_unit_ids`
  - return an empty scope for unauthorized selections
- Use the helper in all report builders that accept `business_unit_id`.
- Fix `_office_bu_time_summary_report` so selected Business Unit ids cannot
  bypass `current_user.scoped_business_unit_ids`.
- Keep cross-office behavior aligned with v6.1:
  - rows may be visible from home-BU or target-project-BU perspective
  - selected BU filtering must still be scoped first

Likely files:

- `apps/core/reports_views.py`
- `tests/test_reports_ui.py`

Acceptance criteria:

- Every report applies server-side scope before request-selected filters.
- Cross-office summary behavior remains as documented.
- CSV export uses the same scoped filter behavior as HTML.

## Phase 2 - Production Authentication Boundary

Goal: replace the development email-entry adapter with a provider boundary that
can support Google SSO and Azure deployment.

Tasks:

- Create an authentication adapter abstraction for external identity claims.
- Keep `CurrentUserService.build_for_employee` as the internal authorization
  source.
- Move the development `validated_email` adapter behind an explicit dev-only
  setting.
- Add a production SSO adapter contract:
  - accepts a trusted authenticated email claim
  - normalizes email
  - initializes the internal TS session
  - audits success and denial
- Document intended Google SSO / Azure ingress behavior.

Likely files:

- `apps/auth/services.py`
- `apps/auth/views.py`
- `apps/auth/middleware.py`
- `config/settings.py`
- `docs/integration-api-spec-v6.1.md`
- new tests in `tests/test_auth_session.py`

Acceptance criteria:

- Local development login remains available only when explicitly enabled.
- Production mode cannot initialize a session from arbitrary posted email.
- Google SSO integration has a clear adapter surface without spreading provider
  logic through the domain.
- Roles continue to come only from TS data.

Implementation note:

- Implemented in Phase 2 on `Codex-5.5` with a provider boundary supporting:
  - `development-email` for local-only `validated_email` entry
  - `trusted-header` for Google SSO / Azure ingress email claims
- `TSMS_ENVIRONMENT=production` disables the development email adapter.
- Session initialization still resolves roles, Office, and Business Unit scope
  exclusively from internal TS data.

## Phase 3 - Azure And Production Settings Readiness

Goal: make deployment safety explicit and environment driven.

Tasks:

- Fail fast when production mode lacks required secrets or host settings.
- Ensure production defaults:
  - `DEBUG=False`
  - no unsafe `SECRET_KEY` fallback
  - secure session cookie
  - secure CSRF cookie
  - HTTPS proxy/security settings documented
  - `CSRF_TRUSTED_ORIGINS` configurable
- Validate PostgreSQL configuration as the intended Azure RDBMS target.
- Add a deployment settings checklist for Azure App Service or Container Apps.
- Define secret storage expectations, preferably Azure Key Vault.

Likely files:

- `config/settings.py`
- `.env.example` if present or a new deployment docs section
- `docs/non-functional-requirements-v6.1.md`
- `docs/integration-api-spec-v6.1.md`

Acceptance criteria:

- App cannot accidentally boot in production with development secrets.
- Azure deployment variables are documented.
- Local SQLite bootstrap still works for development.
- PostgreSQL path is exercised in CI or a documented parity check.

Implementation note:

- Implemented in Phase 3 on `Codex-5.5` with production validation in
  `config/settings.py`.
- Production requires explicit `TSMS_SECRET_KEY`, `TSMS_ALLOWED_HOSTS`,
  PostgreSQL, secure cookies, HTTPS redirect, and proxy SSL header settings.
- Azure deployment settings are documented in
  `docs/deployment/azure-production-checklist.md`.

## Phase 4 - Workflow Concurrency Hardening

Goal: prevent double-submit, conflicting approval decisions, and last-write
workflow updates.

Tasks:

- Add `select_for_update()` around critical records in transactional methods:
  - timesheet create or fetch for edit/submit/withdraw/delete
  - approval item approve/reject
  - submission cycle finalization
  - archive/restore/reopen/admin-withdraw
- Re-check state after locking.
- Add concurrent tests where feasible with transaction test cases.
- Decide whether UI should show a friendly conflict error for stale state.

Likely files:

- `apps/timesheets/services.py`
- `tests/test_timesheet_engine.py`
- `tests/test_approval_worklist_ui.py`

Acceptance criteria:

- Two concurrent approval decisions cannot both succeed.
- Submit/edit races cannot produce submitted timesheets with unexpected line
  replacement.
- Reopen/archive/restore/admin-withdraw transitions are serialized.
- Business errors remain stable and user-facing.

Implementation note:

- Implemented in Phase 4 on `Codex-5.5` by adding lock-aware fetch helpers in
  `apps/timesheets/services.py`.
- Mutating timesheet workflows now request `SELECT FOR UPDATE` on the affected
  weekly timesheet before state checks and writes.
- Approval approve/reject requests lock the parent weekly timesheet, submission
  cycle, and approval item before rechecking approval authority and status.
- Local tests verify the lock calls and stale duplicate approval behavior; true
  concurrent blocking semantics must also be verified on PostgreSQL because
  SQLite ignores `SELECT FOR UPDATE`.

## Phase 5 - Validity Window And Overlap Hardening

Goal: enforce important non-overlap rules safely under concurrency.

Tasks:

- Calendar Period Rules:
  - keep service validation for user-friendly errors
  - add PostgreSQL-safe database enforcement if possible
  - if exclusion constraints are not feasible in SQLite bootstrap, document and
    test database-specific behavior
- Cross-Office Staffing:
  - protect overlapping active staffing windows against concurrent creates
  - evaluate DB exclusion constraints for PostgreSQL
  - otherwise use scoped locking on related project/employee rows during
    staffing writes
- Review normal Project Assignment overlap requirements and either enforce or
  document why overlapping windows are allowed.

Likely files:

- `apps/master_data/models.py`
- new forward migrations
- `apps/master_data/services.py`
- `tests/test_system_management_ui.py`
- `tests/test_timesheet_engine.py`

Acceptance criteria:

- Concurrent overlapping Calendar Period Rule writes cannot both commit.
- Concurrent overlapping Cross-Office Staffing writes cannot both commit.
- SQLite development behavior and PostgreSQL production behavior are both
  understood and tested or documented.

## Phase 6 - Write Path Audit Consistency

Goal: ensure sensitive changes are consistently audited and traceable.

Tasks:

- Add optional `correlation_id` support to `write_audit_event`.
- Review every write path against v6.1 audit expectations:
  - employee identity changes
  - role changes
  - BU scope changes
  - project owner/manager changes
  - staffing changes
  - timesheet lifecycle changes
  - approval decisions
  - guarded deletes
  - imports/exports
- Decide whether timesheet line replacement needs line-level audit or a
  summary audit event.
- Add missing audit tests where gaps are found.

Likely files:

- `apps/audit/models.py`
- `apps/audit/services.py`
- `apps/timesheets/services.py`
- `apps/master_data/services.py`
- related tests

Acceptance criteria:

- Each sensitive operation has actor, target, action, and before/after detail
  where applicable.
- Audit reports remain scoped.
- Correlation id is available for multi-write workflows.

## Phase 7 - Service Boundary Refactor

Goal: reduce module size and isolate bounded contexts without changing
behavior.

Tasks:

- Split `apps/master_data/services.py` into focused modules:
  - offices and countries
  - business units and office configuration
  - employees and transfers
  - clients/categories/cost centers/pricing models
  - general charge codes and approval roles
  - calendars
  - projects and assignments
  - cross-office staffing
- Split report builders from `apps/core/reports_views.py` into report services.
- Move approval scope logic to a neutral policy module to avoid `auth` importing
  from `timesheets`.
- Centralize repeated helpers:
  - reference value lookup
  - date parsing
  - Business Unit scope filtering
  - safe local redirects

Likely files:

- `apps/master_data/services.py`
- new `apps/master_data/services/*.py` or equivalent package structure
- `apps/core/reports_views.py`
- new `apps/core/reports/*.py` or equivalent package structure
- `apps/auth/policies.py`
- `apps/timesheets/approval_scope.py`

Acceptance criteria:

- Behavior remains unchanged under existing tests.
- Import cycles do not increase.
- Future changes can target a bounded module instead of 8k-line services.
- Public service APIs used by views remain stable or are migrated in one pass.

## Phase 8 - Performance And Observability

Goal: prepare for real production data volume.

Tasks:

- Add query-count or performance-sensitive tests for key pages:
  - My Timesheets
  - Approval Worklist
  - Project Time Report
  - Office / BU Time Summary
  - Employee Utilization
- Review indexes for report filters and workflow lookups.
- Optimize Employee Utilization expected-hours calculation to avoid repeated
  per-employee/per-date calendar queries.
- Add structured logging conventions for auth failures, workflow conflicts, and
  report exports.
- Prepare Application Insights or equivalent Azure observability integration.

Likely files:

- `apps/core/reports_views.py`
- `apps/timesheets/services.py`
- model migrations for indexes if needed
- tests for report and approval paths

Acceptance criteria:

- High-traffic reports have bounded query growth.
- Common filters are indexed.
- Production logs can distinguish auth denial, business validation failure, and
  unexpected server error.

## Suggested Implementation Order

1. Phase 0: baseline regression tests.
2. Phase 1: scoped report hardening.
3. Phase 2: authentication adapter boundary.
4. Phase 3: Azure and production settings readiness.
5. Phase 4: workflow row locking.
6. Phase 5: overlap and database constraint hardening.
7. Phase 6: audit consistency.
8. Phase 7: module refactor.
9. Phase 8: performance and observability.

Phases 7 and 8 should wait until security-sensitive behavior is covered by
tests. The refactor phase should be mostly mechanical and should not change
business behavior.

## Definition Of Done For This Program

- All scoped reports resist out-of-scope filter tampering.
- Production mode cannot use development email login accidentally.
- Google SSO has a clean integration boundary.
- Azure deployment settings are documented and fail safe.
- Critical workflow state transitions are serialized.
- Overlapping validity windows are protected under concurrency.
- Sensitive writes are consistently audited.
- Large modules are split without behavior regression.
- Relevant tests pass under SQLite and a PostgreSQL parity run is documented or
  automated.
