# Business Unit Office-Scoped Uniqueness

## 1. Goal

Align Business Unit code uniqueness with Office-scoped administration so a BU code can be reused in different Offices without producing an unreachable duplicate error.

## 2. Current Problem

- `business_unit.bu_code` is globally unique in the schema.
- The Business Unit UI and API are Office-scoped for `TS_ADMIN`.
- A code that already exists in another Office blocks creation, but the blocking record is not visible in the current Office lists.

## 3. Target Behavior

- Business Unit code uniqueness is enforced per Office, not globally.
- A `TS_ADMIN` can create `DELIVERY` in Office B even if `DELIVERY` already exists in Office A.
- A duplicate code inside the same Office is still blocked.
- Validation messages explicitly describe Office-scoped uniqueness.

## 4. Affected Areas

- `apps/master_data/models.py`
- `apps/master_data/migrations/`
- `apps/master_data/services.py`
- `tests/test_business_unit_admin.py`
- v5.4 docs

## 5. Verification

- create BU with same code in a different Office succeeds
- create or rename BU to a duplicate code in the same Office fails
