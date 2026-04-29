# PLANS.md

## Active Plans

- `2026-04-21`: `docs/plans/2026-04-21-phase-2-employee-auth-foundation.md`
  - status: completed
  - focus: internal session initialization, employee/BU scope loading, and backend authorization foundation
- `2026-04-21`: `docs/plans/2026-04-21-phase-2-employee-admin-scope.md`
  - status: completed
  - focus: scoped TS Admin management for employees, roles, and BU assignments
- `2026-04-21`: `docs/plans/2026-04-21-phase-3-classification-masters.md`
  - status: completed
  - focus: scoped TS Admin classification master data for clients, internal categories, cost centers, and general charge codes
- `2026-04-21`: `docs/plans/2026-04-21-phase-4-timesheet-engine.md`
  - status: completed
  - focus: weekly timesheet engine, line validation, day limits, lifecycle, approvals, and admin state transitions
  - progress: milestones 1-7 completed
- `2026-04-22`: `docs/plans/2026-04-22-phase-5-ui-shell-and-navigation.md`
  - status: in progress
  - focus: app shell, access entry, dashboard, profile/session context, and role-aware top-level navigation
  - progress: milestones 1-4 completed; milestone 2 correction pass finished with status filters plus project, project assignment, and calendar period rule management screens; milestone 5 next

## Purpose

Use this file as the standard planning guide and template for non-trivial work in the **Timesheet (TS) Management System** repository.

This file complements `AGENTS.md`.
- `AGENTS.md` defines durable repo-wide implementation rules.
- `PLANS.md` defines how to write and execute task plans.

For feature-specific or task-specific plans, create files in:

```text
/docs/plans/<yyyy-mm-dd>-<short-task-name>.md
```

Example:

```text
/docs/plans/2026-04-20-timesheet-submit-workflow.md
```

---

## When a plan is required

Create or update a plan before coding when the task includes any of these:

- changes in more than 3 modules
- database schema changes
- API changes
- UI changes plus backend changes
- authentication or authorization changes
- approval workflow changes
- data import/export changes
- reporting scope changes
- archive/retention behavior changes
- performance-sensitive work
- refactoring where behavior must remain stable
- unclear, ambiguous, or partially conflicting requirements

For small isolated changes, a full plan may not be necessary.

---

## Planning principles

1. Keep plans short, concrete, and executable.
2. Prefer incremental delivery over large rewrites.
3. State assumptions explicitly.
4. Identify the source documents that govern the task.
5. Call out schema, auth, audit, and workflow impact early.
6. Include the tests required to prove the change.
7. Update the plan if implementation reality changes.
8. Do not use a plan as a substitute for doing the work.

---

## Source-of-truth order for planning

When writing a plan, use this priority:

1. explicit user task instructions
2. approved spec docs in `/docs`
3. `AGENTS.md`
4. existing code constraints

If sources conflict:
- choose the safer, narrower behavior
- record the conflict in the plan
- avoid inventing broader permissions or looser workflow behavior

---

## Required planning checklist

Every plan should explicitly consider these questions:

### Product and business behavior
- What exact user/business problem is being solved?
- Which spec documents govern this task?
- What business rules are affected?
- Are there workflow or state-transition changes?

### Data model
- Are schema changes needed?
- Are new reference values needed?
- Are migrations required?
- Is backfill or data correction required?

### Authorization and security
- Which roles are affected?
- Does row-level scope change?
- Are there sensitive actions involved?
- Are audit events required?

### API and integration
- Are endpoints added or changed?
- Are DTOs or error codes changing?
- Are imports/exports or jobs affected?
- Is idempotency relevant?

### UI and UX
- Which screens are affected?
- Do menu visibility rules change?
- Are there new buttons, filters, or status-dependent states?
- Are there validation messages to add?

### Testing
- Which unit tests are needed?
- Which integration tests are needed?
- Which E2E flows are affected?
- What regression risks should be covered?

### Delivery risk
- What could break?
- Is rollout sequencing required?
- Are feature flags needed?
- Are follow-up tasks likely?

---

## Plan file naming

Use this format:

```text
/docs/plans/<yyyy-mm-dd>-<short-kebab-name>.md
```

Examples:
- `docs/plans/2026-04-20-employee-import-validation.md`
- `docs/plans/2026-04-20-project-scope-inquiry.md`
- `docs/plans/2026-04-20-approval-routing-mixed-mode.md`

Keep names short and outcome-focused.

---

## Standard plan template

Copy this template for each new plan.

```md
# <Plan Title>

## 1. Goal

Describe the outcome in one or two sentences.

## 2. Scope

In scope:
- ...

Out of scope:
- ...

## 3. Source documents

- docs/functional-spec-v5.1.md
- docs/use-cases-acceptance-v5.1.md
- docs/data-model-erd.md
- docs/authorization-matrix.md
- docs/ui-screen-spec.md
- docs/integration-api-spec.md
- docs/business-rules-catalog.md
- docs/non-functional-requirements.md
- AGENTS.md

List only the documents relevant to this task.

## 4. Current state

Summarize the current implementation or repo state.

## 5. Target behavior

Describe the intended behavior after the change.

## 6. Affected areas

Backend modules:
- ...

Frontend screens/features:
- ...

Database / migrations:
- ...

APIs:
- ...

Jobs / integrations:
- ...

## 7. Business rules impacted

- BR-...
- BR-...

## 8. Authorization impact

Roles affected:
- USER
- TS_ADMIN
- PROJECT_OWNER
- PROJECT_MANAGER

Scope impact:
- self
- assigned BU
- owned project
- managed project

State clearly whether scope rules change or remain unchanged.

## 9. Data model changes

- migration needed: yes/no
- tables affected:
- constraints affected:
- reference data seed changes:
- backfill needed: yes/no

## 10. API changes

Endpoints to add/change:
- ...

Request/response changes:
- ...

Error codes:
- ...

OpenAPI updates required:
- yes/no

## 11. UI changes

Screens to add/change:
- ...

New actions:
- ...

Validation messages:
- ...

Role visibility changes:
- ...

## 12. Audit and logging impact

Audit events to add/update:
- ...

Operational logs/metrics:
- ...

## 13. Implementation steps

1. ...
2. ...
3. ...

Keep these steps concrete and ordered.

## 14. Test plan

Unit tests:
- ...

Integration tests:
- ...

E2E tests:
- ...

Manual verification:
- ...

## 15. Risks and mitigations

- Risk: ...
  - Mitigation: ...

## 16. Rollout / deployment notes

- feature flag needed: yes/no
- migration sequencing:
- seed sequencing:
- backward compatibility considerations:

## 17. Open questions / assumptions

- ...

## 18. Definition of done

- code implemented
- tests added/updated
- migrations added if needed
- OpenAPI updated if needed
- audit coverage added
- docs updated where required
```

---

## Lightweight plan template

Use this only for small but still multi-step work.

```md
# <Plan Title>

## Goal
- ...

## Affected modules
- ...

## Main changes
1. ...
2. ...
3. ...

## Risks
- ...

## Tests
- ...
```

---

## Task execution rules

When implementing from a plan:

1. Re-read only the documents relevant to the task.
2. Follow the ordered implementation steps.
3. Update the plan if the implementation path changes.
4. Keep changes small and reviewable where possible.
5. Do not silently expand scope beyond the plan.
6. If a blocker appears, document it in the plan.

---

## Required plan sections for sensitive work

For these task types, the full template is mandatory:

### Authentication / authorization changes
Must include:
- roles affected
- scope affected
- denied-access cases
- backend enforcement points
- regression tests for data leakage prevention

### Workflow / approval changes
Must include:
- state transitions impacted
- approval routing changes
- audit implications
- backward-compatibility implications for existing records

### Schema changes
Must include:
- migration design
- rollback or forward-fix notes
- seed/reference-data changes
- data backfill notes

### Import / export changes
Must include:
- idempotency behavior
- job tracking changes
- error handling changes
- file/payload format changes

---

## Plan review checklist

Before starting implementation, confirm the plan answers these:

- Is the goal specific?
- Is scope bounded?
- Are source docs listed?
- Are affected modules identified?
- Are business rules listed?
- Is auth/scope impact addressed?
- Are schema/API/UI changes called out?
- Are tests listed?
- Are risks noted?
- Are assumptions explicit?

If not, refine the plan first.

---

## Example mini plan

```md
# Timesheet Submit Validation Tightening

## Goal
Prevent submission when required custom attributes are missing and surface stable validation errors.

## Affected modules
- apps/api timesheets
- apps/api shared validation
- apps/web timesheet editor

## Main changes
1. Enforce required custom attributes in backend submit validation.
2. Return stable error code and field mapping.
3. Show field-level and banner-level error messages in the editor.

## Risks
- Existing draft timesheets may fail submit after the change.

## Tests
- unit tests for attribute validator
- integration tests for submit failure
- E2E test for employee submit with missing attribute
```

---

## Relationship to task summaries

A plan is not the same as the end-of-task summary.

After implementation, still provide a task summary with:
- what changed
- files changed
- migrations added
- tests added/updated
- commands run
- result
- open issues

---

## Keep plans current

If implementation differs materially from the original plan:
- update the plan file
- note what changed
- keep obsolete steps clearly marked or removed

Plans should reflect reality, not intention alone.
