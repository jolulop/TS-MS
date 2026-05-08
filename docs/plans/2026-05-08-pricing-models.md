# Pricing Model Master Data

## 1. Goal

Add a new office-level Pricing Model master and make Project pricing model selection mandatory across schema, API, System Management UI, and seed/test data.

## 2. Scope

In scope:
- add a `PricingModel` master table with audit fields
- add a mandatory `pricing_model` foreign key on `Project`
- add Pricing Model CRUD flows to System Management for `TS_ADMIN`
- require Pricing Model selection in project create/update UI and API
- update seed data, helpers, and tests

Out of scope:
- pricing calculations or billing logic
- project deletion behavior
- role or scope model changes

## 3. Source documents

- docs/functional-spec-v5.2.md
- docs/ui-screen-spec-v5.2.md
- docs/integration-api-spec-v5.2.md
- docs/database-schema-diagram.md
- AGENTS.md

## 4. Design notes

- Treat Pricing Models like other office-level masters such as Clients and Cost Centers.
- `TS_ADMIN` access remains scoped to the active Office.
- Deletion will be guarded only by referential integrity, with no cascade cleanup.
- The mandatory Project relationship will be enforced in backend validation and mirrored in the UI.

## 5. Affected modules

- `apps/master_data/models.py`
- `apps/master_data/services.py`
- `apps/master_data/views.py`
- `apps/master_data/urls.py`
- `apps/master_data/admin.py`
- `apps/master_data/management/commands/seed_dev_data.py`
- `apps/core/system_views.py`
- `apps/core/views.py`
- `apps/core/urls.py`
- `tests/helpers.py`
- `tests/test_system_management_ui.py`
- `tests/test_phase5_system_management_extensions.py`
- supporting tests that build Projects

## 6. Schema changes

- add `PricingModel`
- add `Project.pricing_model`
- add a forward migration that seeds each existing Office with a fallback default pricing model and backfills existing Projects

## 7. API changes

- add Pricing Model collection/detail admin endpoints
- require `pricing_model_id` on project creation
- allow `pricing_model_id` updates on project edit
- include serialized pricing model data in project responses

## 8. UI changes

- add Pricing Models to the System Management hub and side navigation
- add Pricing Model collection/detail screens with CRUD
- add mandatory Pricing Model select field to project create/edit forms
- show Pricing Model in project detail

## 9. Tests

- Pricing Model CRUD via System Management
- Pricing Model CRUD via API if applicable
- project create/update through HTML with pricing model
- project create via API requires pricing model
- delete blocked when referenced by a project
- seed/test helper coverage for mandatory project pricing model

## 10. Risks

- existing project creation helpers and seed paths will break until all callers are updated
- backfill behavior for existing Projects must be deterministic and safe
