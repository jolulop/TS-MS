# Reference Data Strategy

## Purpose

Reference data in this repository is mandatory system data, not sample/demo content.

The repository seeds the ERD-backed domain/value structure required by implemented TS authorization, workflow, configuration, calendar, and audit features.

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
- Separate developer sample-data command: `python manage.py seed_dev_data`

The command uses update-or-create semantics keyed by:

- domain: `domain_code`
- value: `(domain, value_code)`

## Why this matters

The implemented product depends on stable domains and coded values for internal authorization, lifecycle handling, approval processing, Office configuration, calendar rules, integration jobs, and audit events.

## Future additions

This strategy can still be extended with:

- richer metadata per domain
- validation around reserved codes
- separate sample data commands for developer/demo environments

## Developer sample data

Local browsing and demos should use the separate `seed_dev_data` command, not the mandatory
reference-data seed.

Current dev sample seed behavior:
- loads reference data first
- creates sample Offices, Office configuration, Business Units, employees, roles, and scope assignments
- creates sample Yearly Calendars, Calendar Period Rules, and supporting calendar reference data
- creates sample Clients, Internal Categories, Cost Centers, Pricing Models, General Charge Codes, and Projects
- is idempotent and keyed by stable business codes

Current TS Admin sample login:
- `jose.luis.lopez@timia.ai`
