# AGENTS.md

## Purpose

This repository contains the **Timesheet (TS) Management System**.

Codex should treat this file as the repository-level implementation guide. Follow it before making changes.

The primary source documents for product behavior are:

1. `docs/functional-spec-v5.1.md`
2. `docs/use-cases-acceptance-v5.1.md`
3. `docs/data-model-erd.md`
4. `docs/authorization-matrix.md`
5. `docs/ui-screen-spec.md`
6. `docs/integration-api-spec.md`
7. `docs/business-rules-catalog.md`
8. `docs/non-functional-requirements.md`

If code and docs conflict, do **not** silently guess. Prefer the newest approved spec doc, then align code to it.

---

## Product summary

Build and maintain a web-based enterprise Timesheet Management System with two functional blocks:

- **System Management**
- **TS Management**

Core business themes:

- weekly Monday-Friday timesheets
- employee/project/general-code time charging
- internal role-based authorization after external email validation
- project owner / project manager / TS administrator roles
- Business Unit scoped administration
- approval workflows
- auditability
- retention and archive

---

## Mandatory business rules

These are non-negotiable unless a newer approved spec changes them.

### Authentication and authorization

- External access validation is used **only once at access time** to validate the user email.
- After access validation, the TS system identifies the user internally using `employee.email`.
- All post-login authorization is handled **internally**.
- Roles come from TS data, not from the external validation system.
- Supported internal roles:
  - `USER`
  - `TS_ADMIN`
  - `PROJECT_OWNER`
  - `PROJECT_MANAGER`
- Deny by default.
- Row-level scope must be enforced server-side.

### Timesheet rules

- One employee can have at most one weekly timesheet per week.
- A timesheet week is Monday to Friday only.
- Weekend entry is not allowed in the standard timesheet.
- Employees can charge only to:
  - active assigned projects for the work date, or
  - valid general charge codes for the work date.
- Daily hour limits come from the effective calendar period rule.
- Approved timesheets are locked.
- Archived timesheets are not editable.

### Project rules

- Projects belong to one Business Unit.
- Project owner must have the `PROJECT_OWNER` role.
- Project manager must have the `PROJECT_MANAGER` role.
- `client`, `internal category`, and `cost center` are mandatory on every project.
- Closed projects cannot receive new time after close date.

### Administrative scope

- TS Admins act only within assigned Business Units.
- Project Owners act within owned-project scope.
- Project Managers act within managed-project scope.

### Audit

Always preserve auditability for:

- employee identity changes
- role changes
- BU scope changes
- project ownership/management changes
- timesheet submit/withdraw/reopen
- approval approve/reject
- archive/restore
- imports/exports

---

## Implementation defaults

If the repository does not already define a different stack, use these defaults.

### Backend

- **TypeScript**
- **Node.js LTS**
- **NestJS** for API/application layer
- **PostgreSQL** for persistence
- **Prisma** or **TypeORM** for ORM/migrations
- **OpenAPI** generation for REST contracts

### Frontend

- **TypeScript**
- **React**
- **Next.js** or **Vite + React Router**
- component-driven UI
- accessible form and table primitives

### Testing

- unit tests for business services and validators
- integration tests for API + DB flows
- end-to-end tests for core user journeys

### Packaging

Prefer a monorepo:

- `apps/web`
- `apps/api`
- `packages/shared-types`
- `packages/eslint-config`
- `packages/tsconfig`
- `docs`
- `db`

If the repo already exists with a different layout, follow the existing layout instead of forcing this one.

---

## Recommended repository layout

If bootstrapping from scratch, use:

```text
/docs
  functional-spec-v5.1.md
  use-cases-acceptance-v5.1.md
  data-model-erd.md
  authorization-matrix.md
  ui-screen-spec.md
  integration-api-spec.md
  business-rules-catalog.md
  non-functional-requirements.md
  decisions/
  plans/

/apps
  /api
    /src
      /modules
        /auth
        /employees
        /business-units
        /calendars
        /clients
        /internal-categories
        /cost-centers
        /general-charge-codes
        /projects
        /project-assignments
        /timesheets
        /approvals
        /reports
        /integrations
        /reference-data
        /audit
  /web
    /src
      /app or /pages
      /features
      /components
      /hooks
      /lib
      /routes

/packages
  /shared-types
  /shared-validation
  /shared-auth

/db
  /migrations
  /seed
  /schemas

/tests
  /integration
  /e2e
```

---

## Source-of-truth order

When implementing behavior, use this priority:

1. explicit user task instructions
2. approved latest spec documents in `/docs`
3. this `AGENTS.md`
4. existing code conventions

If specs conflict with each other, do not choose arbitrarily. Leave a note in the task summary and implement the safer, narrower behavior.

---

## How Codex should work in this repo

### 1. Read before changing code

Before implementing a feature, read only the docs and code relevant to the task. Do not scan the entire repo unless needed.

### 2. Plan first for multi-step work

Create or update a plan in `docs/plans/` when the task is:

- ambiguous
- cross-module
- larger than one small PR
- schema-changing
- auth/security-sensitive
- workflow-changing

Use a file named like:

- `docs/plans/<yyyy-mm-dd>-<short-task-name>.md`

The plan should include:

- goal
- affected modules
- schema changes
- API changes
- UI changes
- tests to add
- rollout risks

### 3. Make small, reviewable changes

Prefer incremental changes over large rewrites.

### 4. Keep business logic out of controllers and components

- Backend controllers should stay thin.
- Frontend pages should stay thin.
- Put business rules in dedicated services/policies/validators.

### 5. Never duplicate authorization logic casually

Centralize authorization in reusable policy code.

### 6. Never trust UI-only validation

Any rule enforced in the UI must also be enforced in backend validation.

---

## Architecture rules

### Domain modules

Keep business modules separated. Do not mix unrelated logic across modules.

Preferred backend module boundaries:

- `auth`
- `employees`
- `business-units`
- `reference-data`
- `calendars`
- `clients`
- `internal-categories`
- `cost-centers`
- `general-charge-codes`
- `projects`
- `project-assignments`
- `timesheets`
- `approvals`
- `reports`
- `integrations`
- `audit`

### Domain services

Every module should have clear service boundaries.

Examples:

- `TimesheetValidationService`
- `AuthorizationPolicyService`
- `ApprovalRoutingService`
- `CalendarRuleResolver`
- `AuditWriter`
- `IntegrationJobService`

### Transactions

Use transactional boundaries for critical state transitions:

- submit timesheet
- approve/reject approval item
- reopen timesheet
- archive/restore
- employee import batch row persistence where needed

---

## Authorization implementation rules

### Core policy

All post-login authorization is internal.

Use internal sources only:

- employee status
- employee roles
- employee BU scope
- project owner relationship
- project manager relationship
- timesheet ownership
- entity state

### Required policy helpers

Implement centralized policy methods such as:

- `canViewEmployee(currentUser, employeeId)`
- `canManageEmployee(currentUser, employeeId)`
- `canViewProject(currentUser, projectId)`
- `canManageProject(currentUser, projectId)`
- `canViewTimesheet(currentUser, timesheetId)`
- `canEditTimesheet(currentUser, timesheetId)`
- `canSubmitTimesheet(currentUser, timesheetId)`
- `canApproveApprovalItem(currentUser, approvalItemId)`
- `canRejectApprovalItem(currentUser, approvalItemId)`
- `canReopenTimesheet(currentUser, timesheetId)`
- `canRunReport(currentUser, reportCode, filters)`

### Row-level filtering

Never fetch all rows and filter in memory for security-sensitive data.
Apply scope in DB queries.

Examples:

- employee self view: `employee_id = currentUser.id`
- PM approvals: `project.project_manager_employee_id = currentUser.id`
- PO inquiry: `project.project_owner_employee_id = currentUser.id`
- TS Admin BU scope: `business_unit_id IN (...)`

### Safe visibility default

For Project Owners and Project Managers, default to showing only scoped lines, not unrelated timesheet lines.

---

## Data model rules

Follow the ERD and preserve these constraints.

### Required hard constraints

- unique employee email strategy (`canonical_email` recommended)
- one primary BU per employee
- one weekly timesheet per employee/week
- exactly one charging target on a timesheet line: project xor general charge code
- no overlapping calendar period rules in the same calendar
- mandatory project classification fields
- immutable or append-only approval action history

### Soft delete / status strategy

Prefer status-based lifecycle over hard delete.
Do not physically delete transactional records unless explicitly required by an approved spec.

### Migrations

- Use versioned DB migrations.
- Do not edit old applied migrations.
- Add forward-only migrations.
- Include seed updates for required reference data.

---

## API rules

### Style

- REST + JSON
- versioned base path: `/api/v1`
- structured error responses
- OpenAPI generated and kept current

### Required standards

- validate request DTOs
- map business-rule failures to stable error codes
- keep controllers thin
- do not expose unauthorized rows
- support pagination for list endpoints
- support filters documented in the spec

### Error handling

Use stable error codes for business failures. Do not return unstructured raw exceptions to clients.

### Idempotency

Support idempotency where specified for:

- imports
- exports
- sync operations
- submit/reopen where relevant

---

## UI rules

### General

Implement the two-block navigation exactly:

- `System Management`
- `TS Management`

### Visibility

- hide unauthorized menus and actions
- backend remains authoritative
- use read-only states where users may view but not edit

### Forms

- show field-level validation when possible
- show banner-level business-rule errors for workflow failures
- make status read-only when state should not be changed directly

### Tables/lists

All main lists should support:

- pagination
- sorting
- filtering
- empty states
- export when allowed

### Accessibility

Favor semantic HTML and keyboard-friendly interactions.

---

## Testing rules

Codex should add or update tests whenever behavior changes.

### Required test layers

#### Unit tests

For:

- validators
- policy services
- approval routing
- lifecycle transitions
- date and calendar rule resolution

#### Integration tests

For:

- employee CRUD/import
- project and assignment rules
- timesheet create/save/submit
- approve/reject
- reopen/archive/restore
- reporting scope enforcement
- API authorization

#### End-to-end tests

For the main flows:

- login/session initialization
- user creates and submits timesheet
- PM approves/rejects
- admin reopens timesheet
- admin imports employees

### Minimum rule

No change is complete until the most relevant tests are added or updated.

---

## Definition of done

A task is done only when all of the following are true:

1. behavior matches the applicable specs
2. code compiles
3. relevant tests pass
4. new or changed business rules are covered by tests
5. authorization checks are enforced server-side
6. audit events are added for sensitive operations
7. migrations and seed data are included when schema/reference data changes
8. OpenAPI or API docs are updated when API behavior changes
9. UI states match role and status rules
10. task summary explains what changed, how it was verified, and any open issues

---

## Required engineering conventions

### TypeScript

- prefer strict typing
- avoid `any`
- use explicit DTOs and domain types
- keep functions small and named for business meaning

### Naming

- use business-language names from the spec
- avoid ambiguous abbreviations except `TS` where already established
- keep error codes stable once introduced

### Comments

Add comments only where intent is not obvious from code.
Do not write decorative comments.

### Logging

- use structured logs
- do not log secrets
- include request/job correlation identifiers where available

---

## Audit rules

Always write audit events for:

- employee email changes
- role changes
- BU assignment changes
- project owner/manager changes
- timesheet submit
- approval approve/reject
- withdraw/reopen
- archive/restore
- imports/exports
- denied sensitive actions where policy requires it

Audit entries should include:

- actor
- timestamp
- entity name/id
- action
- before/after where relevant
- reason where relevant
- correlation id where available

---

## Integration rules

### Jobs

All imports/exports/syncs should create tracked jobs.

### Failure handling

- preserve valid committed data
- record row-level errors when applicable
- avoid partial silent failures

### Leave import

If leave conflicts with manual time, raise the configured conflict rather than guessing.

---

## Things Codex must not do

- Do not bypass authorization checks for speed.
- Do not implement UI-only security.
- Do not hardcode role names in many places; centralize them.
- Do not hard-delete timesheets, approvals, or audit history unless explicitly specified.
- Do not rewrite major modules when a targeted change is enough.
- Do not silently change business rules to make implementation easier.
- Do not expose unrelated timesheet lines to PO/PM by default.
- Do not introduce schema changes without migrations.
- Do not leave TODOs in shipped business-critical paths without clearly calling them out.

---

## Commands Codex should use

If these scripts exist, prefer them. If they do not exist yet, add them consistently.

### Install

```bash
pnpm install
```

### Start local dev

```bash
pnpm dev
```

### Backend tests

```bash
pnpm test:api
```

### Frontend tests

```bash
pnpm test:web
```

### Full test suite

```bash
pnpm test
```

### Lint

```bash
pnpm lint
```

### Typecheck

```bash
pnpm typecheck
```

### Build

```bash
pnpm build
```

### E2E

```bash
pnpm test:e2e
```

### Database migrations

```bash
pnpm db:migrate
pnpm db:seed
```

If the repo uses `npm`, `yarn`, `turbo`, `nx`, `poetry`, `make`, or another tool instead, follow the repo’s existing convention and update this file.

---

## Recommended first build order

If bootstrapping the system from scratch, build in this order:

1. repo scaffolding and shared configs
2. auth/session initialization
3. reference data + seed data
4. employee + BU + role model
5. project classification masters
6. project + assignment model
7. calendar model and validation services
8. timesheet + timesheet lines
9. submit workflow
10. approval workflow
11. reporting basics
12. imports/exports
13. archive/admin operations
14. polish UI and observability

---

## When to create a plan file

Create a plan file before coding if the task includes any of these:

- more than 3 modules changed
- database migration + API + UI together
- auth or security changes
- approval workflow changes
- data import/export changes
- refactoring with behavior preservation requirements
- unclear or conflicting requirements

The plan should be concise, actionable, and updated if the implementation path changes.

---

## Task summary format

At the end of each substantial task, provide a short summary with:

- what changed
- files changed
- migrations added
- tests added/updated
- commands run
- result
- open issues or follow-up risks

---

## If documentation is missing

If a task needs missing details:

1. infer the safest narrow behavior from current specs
2. implement that behavior cleanly
3. note the assumption clearly in the task summary
4. do not invent broad permissions or irreversible business behavior

---

## Keep this file practical

If repeated mistakes appear during development, update this file with a concrete new rule.
