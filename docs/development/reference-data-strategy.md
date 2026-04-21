# Reference Data Strategy

## Purpose

Reference data in this repository is mandatory system data, not sample/demo content.

Phase 1 seeds the ERD-backed domain/value structure required by future TS authorization, workflow, configuration, and audit features.

## Rules

- Keep reference data in version-controlled code or manifests.
- Seed by stable business code, not by display label.
- Make the seed command idempotent.
- Keep reference data separate from optional sample data.
- Update reference-data seeds intentionally when specs add or rename stable codes.

## Current implementation

- Models:
  - `apps.reference_data.models.RefDomain`
  - `apps.reference_data.models.RefValue`
- Seed manifest: `apps.reference_data.seeds.REFERENCE_DATA`
- Seed command: `python manage.py seed_reference_data`

The command uses update-or-create semantics keyed by:

- domain: `domain_code`
- value: `(domain, value_code)`

## Why this matters

Later phases will depend on stable domains and coded values for internal authorization, lifecycle handling, approval processing, configuration, integration jobs, and audit events. The foundation phase needs a stable place for that system data before domain features are added.

## Future additions

When business modules arrive, this strategy can be extended with:

- richer metadata per domain
- validation around reserved codes
- separate sample data commands for developer/demo environments
