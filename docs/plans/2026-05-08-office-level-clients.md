# Office-Level Clients

## 1. Goal

Move Clients from Business Unit scope to Office scope so `TS_ADMIN` users manage Clients at the Office level without assigning them to a Business Unit.

## 2. Scope

In scope:
- remove the Client to Business Unit database relationship
- update Client create and update flows in UI and JSON admin endpoints
- change Client list and detail authorization from Business Unit scoped to Office scoped
- update project validation so project clients only need to belong to the same Office
- update seed helpers, schema documentation, and tests

Out of scope:
- moving Internal Categories or Cost Centers to Office scope
- changing unrelated project classification rules
- adding new Client lifecycle behavior

## 3. Source documents

- 2026-05-08 user change request in this task
- `AGENTS.md`
- `PLANS.md`
- current Client and Project management implementation

## 4. Current state

- `Client` belongs to both `BusinessUnit` and `Office`.
- Client create UI asks for a Business Unit.
- Client list and detail access is limited by Business Unit scope.
- Project validation requires client, internal category, and cost center to belong to the same Business Unit as the project.

## 5. Target behavior

- `Client` belongs only to `Office`.
- Client create and update no longer accept or show Business Unit.
- Any `TS_ADMIN` operating inside the active Office can manage Office-level Clients there.
- Parent Client validation becomes same-Office validation.
- Project validation requires:
  - client belongs to the same Office as the project
  - internal category belongs to the same Business Unit as the project
  - cost center belongs to the same Office as the project

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

- drop `client.business_unit_id`
- replace the Client uniqueness rule from Business Unit scope to Office scope

## 8. Authorization and audit

- `TS_ADMIN` remains the acting role
- Client visibility and management become Office scoped rather than Business Unit scoped
- audit events remain required for Client create and update

## 9. Tests

- Client UI and API create without Business Unit
- Client list visible across Business Unit scopes within the same Office
- Project validation accepts same-Office Client from another Business Unit
- regressions for parent Client validation and client detail rendering

## 10. Risks and assumptions

- Assumption: once Clients become Office-level, `client_code` should be unique within an Office because Business Unit is no longer available as part of the uniqueness key.
- Risk: existing seed and tests often create Clients through a Business Unit helper, so they all need coordinated updates to avoid partial breakage.

## 11. Implementation status

Status:
- completed

Delivered:
- `Client` now belongs only to `Office`
- Client create and update no longer require or accept a Business Unit
- Client list and detail access are now Office scoped for `TS_ADMIN`
- parent Client validation now works at Office level
- project validation now requires the Client and Cost Center to belong to the same Office while Internal Category remains Business Unit scoped
- migrations, schema docs, and regression tests were updated
