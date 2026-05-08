# Office-Level Cost Centers

## 1. Goal

Move Cost Centers from Business Unit scope to Office scope so `TS_ADMIN` users manage Cost Centers at the Office level without assigning them to a Business Unit.

## 2. Scope

In scope:
- remove the Cost Center to Business Unit database relationship
- update Cost Center create and update flows in UI and JSON admin endpoints
- change Cost Center list and detail authorization from Business Unit scoped to Office scoped
- update project validation so project cost centers only need to belong to the same Office
- update seed helpers, schema documentation, and tests

Out of scope:
- moving Internal Categories to Office scope
- changing unrelated project classification rules
- adding Cost Center delete behavior

## 3. Source documents

- 2026-05-08 user change request in this task
- `AGENTS.md`
- `PLANS.md`
- current Cost Center and Project management implementation

## 4. Current state

- `CostCenter` belongs to both `BusinessUnit` and `Office`.
- Cost Center create UI asks for a Business Unit.
- Cost Center list and detail access is limited by Business Unit scope.
- Project validation requires internal category and cost center to belong to the same Business Unit as the project.

## 5. Target behavior

- `CostCenter` belongs only to `Office`.
- Cost Center create and update no longer accept or show Business Unit.
- Any `TS_ADMIN` operating inside the active Office can manage Office-level Cost Centers there.
- Project validation requires:
  - client belongs to the same Office as the project
  - cost center belongs to the same Office as the project
  - internal category still belongs to the same Business Unit as the project

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/core`

Supporting artifacts:
- migrations
- seed helpers
- schema docs
- tests

## 7. Schema changes

- drop `cost_center.business_unit_id`
- replace the Cost Center uniqueness rule from Business Unit scope to Office scope

## 8. Authorization and audit

- `TS_ADMIN` remains the acting role
- Cost Center visibility and management become Office scoped rather than Business Unit scoped
- audit events remain required for Cost Center create and update

## 9. Tests

- Cost Center UI and API create without Business Unit
- Cost Center list visible across Business Unit scopes within the same Office
- Project validation accepts same-Office Cost Center from another Business Unit
- regressions for Cost Center detail rendering and office write blocking

## 10. Risks and assumptions

- Assumption: once Cost Centers become Office-level, `cost_center_code` should be unique within an Office because Business Unit is no longer available as part of the uniqueness key.
- Risk: existing seed and tests often create Cost Centers through a Business Unit helper, so they all need coordinated updates to avoid partial breakage.

## 11. Implementation status

Status:
- completed

Delivered:
- `CostCenter` now belongs only to `Office`
- Cost Center create and update no longer require or accept a Business Unit
- Cost Center list and detail access are now Office scoped for `TS_ADMIN`
- project validation now requires the Cost Center to belong to the same Office while Internal Category remains Business Unit scoped
- migrations, schema docs, and regression tests were updated
