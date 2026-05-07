# Office Rename

## 1. Goal

Rename the existing Country entity to Office across the database schema, backend models and payloads, and System Management/UI text without changing any business behavior or authorization rules.

## 2. Scope

In scope:
- rename the `country` table to `office`
- rename `country_name` to `office_name`
- rename model and foreign-key field usage from Country/country to Office/office
- update authenticated session payloads and admin API payloads to use `office`
- rename System Management routes, labels, and screen text from Country to Office
- update seed/dev data and automated tests for the new naming

Out of scope:
- changing business rules, permissions, or row-level scope behavior
- introducing new Office attributes or workflows
- broad reference-data code renames where the existing internal code can stay behaviorally identical

## 3. Source documents

- 2026-05-07 user change request in this task
- `AGENTS.md`
- existing approved country-management implementation in the repo

## 4. Current state

- `Country` is the top-level scoped entity across master data, session context, and System Management.
- The schema, models, UI copy, request/response payloads, and seed data all currently use country naming.
- Existing authorization and data-scoping behavior already relies on this entity and must remain unchanged.

## 5. Target behavior

- The same data and workflows remain available, but they are now presented and persisted as Office.
- Database objects use `office` / `office_name`.
- Screen labels, routes, form fields, and serialized payloads use `office` / `office_name`.
- Existing active/inactive lifecycle behavior continues unchanged.

## 6. Affected areas

Backend modules:
- `apps/master_data`
- `apps/auth`
- `apps/core`

Supporting artifacts:
- seed/dev data
- schema documentation
- tests

## 7. Schema changes

- rename model `Country` to `Office`
- rename DB table `country` to `office`
- rename column `country_name` to `office_name`
- rename dependent foreign-key fields from `country` to `office`

## 8. Tests

- auth/session payload coverage
- System Management Office UI flows
- admin API tests for renamed Office payloads
- regression coverage for country-scoped behavior now exposed as office-scoped behavior

## 9. Risks and assumptions

- Assumption: internal reference-data codes such as `COUNTRY_STATUS` may remain unchanged where they are not part of the public schema or API contract, because the request is a naming change for entity/table/field/UI/API behavior rather than a business-rule rewrite.
- Risk: this rename touches many related foreign keys and session helpers, so partial renames could break authorization or templates. The change should be applied consistently and verified with focused tests.
