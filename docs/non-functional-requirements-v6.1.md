# Non-Functional Requirements v6.1

## 1. Security

- all post-login authorization is internal
- production authentication must use a trusted external identity claim boundary
  rather than browser-posted email values
- local development email login must be disabled when
  `TSMS_ENVIRONMENT=production`
- production configuration must fail fast when required secrets, allowed hosts,
  secure-cookie settings, HTTPS proxy settings, or PostgreSQL configuration are
  missing or unsafe
- server-side authorization is mandatory
- deny by default
- do not rely on hidden UI actions for security

## 2. Data Integrity

- use forward-only migrations for schema changes
- preserve referential integrity
- prefer guarded deletes over destructive cascades
- enforce business constraints in backend services

## 2A. Architecture Boundaries

- authorization policy code must not import from the `timesheets` application
  for approval-scope filtering; shared approval-scope helpers live in
  `apps.common`.
- duplicated infrastructure helpers such as request/service parsing,
  reference-value lookup, and safe local path validation should be centralized
  in `apps.common` before adding new call sites.
- master-data service splits should keep `apps.master_data.services` as a
  compatibility export layer until all views and APIs are migrated deliberately.
  This applies to extracted Country, Office, Office Configuration, and Business
  Unit service modules, and to Employee administration/service-boundary modules.

## 3. Auditability

- sensitive administrative and workflow actions must emit audit events
- audit should capture actor, target, action, and before/after details where relevant
- audit events can store an optional correlation identifier for traceability
  across related service operations
- high-volume edits such as timesheet line replacement should use concise
  summary audit events unless a later approved requirement asks for per-line
  history

## 4. Consistency

- UI and backend validations must agree
- Office and Business Unit scope must be applied consistently across UI, API, and reports
- shared System Management create and edit screens should follow the same layout direction where implemented
- critical workflow state transitions must be transactional and request row
  locks for the affected timesheet, submission cycle, or approval item before
  rechecking authorization and state

## 5. Usability

- server-rendered admin screens should provide direct create/edit flows
- detail pages are the main update surface
- collection tables should use clear primary-row navigation without requiring a duplicate visible action column
- blocked actions should return clear user-facing errors

## 6. Maintainability

- business logic should stay in services and policies, not in thin controllers/views
- reusable authorization rules should stay centralized
- markdown repository docs should remain aligned with the implemented code

## 7. Observability

- audit and integration job history must remain reportable
- administrative failures should surface stable error codes or clear UI messages

## 8. Production Deployment

- Azure deployment variables are documented in
  `docs/deployment/azure-production-checklist.md`.
- Production uses PostgreSQL-compatible configuration.
- Workflow row-lock behavior must be validated against PostgreSQL-compatible
  parity environments because SQLite does not enforce `SELECT FOR UPDATE`.
- Validity-window guards for Calendar Period Rules and staffing overlap writes
  use service-level validation plus scoped `SELECT FOR UPDATE` locking. SQLite
  development runs validate behavior but do not prove concurrent blocking;
  Azure/PostgreSQL parity runs must verify the blocking semantics before go-live.
- Production secrets should come from Azure Key Vault or an equivalent managed
  secret store.
- Local SQLite bootstrap remains a development-only path.
