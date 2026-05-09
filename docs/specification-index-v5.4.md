# Specification Index v5.4

## Purpose

This markdown set is the current repository-aligned specification for the implemented Timesheet Management System as of `2026-05-09`.

It supersedes the incremental markdown delta notes in:
- `docs/functional-spec-v5.2.md`
- `docs/ui-screen-spec-v5.2.md`
- `docs/integration-api-spec-v5.2.md`

It also provides a code-aligned working reference alongside the legacy `.docx` documents in this folder.

## v5.4 Documents

- [functional-spec-v5.4.md](/home/jolulop/code/TS-MS/docs/functional-spec-v5.4.md)
- [ui-screen-spec-v5.4.md](/home/jolulop/code/TS-MS/docs/ui-screen-spec-v5.4.md)
- [integration-api-spec-v5.4.md](/home/jolulop/code/TS-MS/docs/integration-api-spec-v5.4.md)
- [authorization-matrix-v5.4.md](/home/jolulop/code/TS-MS/docs/authorization-matrix-v5.4.md)
- [business-rules-catalog-v5.4.md](/home/jolulop/code/TS-MS/docs/business-rules-catalog-v5.4.md)
- [use-cases-acceptance-v5.4.md](/home/jolulop/code/TS-MS/docs/use-cases-acceptance-v5.4.md)
- [non-functional-requirements-v5.4.md](/home/jolulop/code/TS-MS/docs/non-functional-requirements-v5.4.md)
- [data-model-erd-v5.4.md](/home/jolulop/code/TS-MS/docs/data-model-erd-v5.4.md)
- [database-schema-diagram.md](/home/jolulop/code/TS-MS/docs/database-schema-diagram.md)

## Version Notes

v5.4 captures these major implemented changes relative to the older baseline docs:
- Country was renamed to Office.
- Office-level configuration replaced Business Unit-owned configuration.
- Office creation now bootstraps an initial Business Unit and Office admin employee.
- Clients and Cost Centers are now Office-level masters.
- Pricing Models were added as a new Office-level master.
- Projects now require a Pricing Model.
- System Management now includes Office, Project, Project Assignment, Calendar Period Rule, and Pricing Model management.
- Guarded delete actions exist on selected System Management detail screens.
- Live Project Time Inquiry is available to Project Owners and Project Managers.

## Reading Order

1. Functional specification
2. Authorization matrix
3. Business rules catalog
4. UI screen specification
5. Integration API specification
6. Use cases and acceptance
7. Data model and schema diagram
8. Non-functional requirements
