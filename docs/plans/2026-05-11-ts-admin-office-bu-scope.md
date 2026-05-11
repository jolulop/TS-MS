# TS Admin Office BU Scope

## 1. Goal

Remove the Business Unit orphaning catch-22 by enforcing that active `TS_ADMIN` employees always keep full Business Unit scope for their active Office.

## 2. Source Documents

- `docs/functional-spec-v5.4.md`
- `docs/use-cases-acceptance-v5.4.md`
- `docs/authorization-matrix-v5.4.md`
- `docs/business-rules-catalog-v5.4.md`
- `AGENTS.md`

## 3. Target Behavior

- Creating a Business Unit automatically adds that Business Unit to every active `TS_ADMIN` employee in the same Office.
- Creating an employee with `TS_ADMIN` automatically gives the employee full Business Unit scope for the Office.
- Adding `TS_ADMIN` to an existing employee automatically expands the employee scope to all Business Units in the Office.
- While an employee still has active `TS_ADMIN`, Business Unit scope saves may change the primary Business Unit but may not narrow the Office-wide scope.
- Existing data is backfilled so previously orphan-risk Business Units become reachable again.

## 4. Affected Areas

- `apps/master_data/services.py`
- `apps/master_data/migrations/`
- `apps/core/system_views.py`
- `tests/test_business_unit_admin.py`
- `tests/test_employee_admin.py`

## 5. Verification

- API tests for Business Unit creation sync
- API tests for employee create and role replacement sync
- API tests for TS Admin scope edits keeping full Office scope

## 6. Risks And Assumptions

- This intentionally broadens effective `TS_ADMIN` reach from selected Business Units to all Business Units in the active Office.
- Existing sessions still derive scope from current database rows on each request, so the migration and service sync are both needed to avoid stale orphan situations.
