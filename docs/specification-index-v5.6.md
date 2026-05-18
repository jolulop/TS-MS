# Specification Index v5.6

## Purpose

This markdown set is the current repository-aligned specification for the implemented Timesheet Management System as of `2026-05-17`.

It supersedes the incremental markdown delta notes in:
- `docs/functional-spec-v5.2.md`
- `docs/ui-screen-spec-v5.2.md`
- `docs/integration-api-spec-v5.2.md`

It also provides a code-aligned working reference alongside the legacy `.docx` documents in this folder.

## v5.6 Documents

- [functional-spec-v5.6.md](/home/jolulop/code/TS-MS/docs/functional-spec-v5.6.md)
- [ui-screen-spec-v5.6.md](/home/jolulop/code/TS-MS/docs/ui-screen-spec-v5.6.md)
- [integration-api-spec-v5.6.md](/home/jolulop/code/TS-MS/docs/integration-api-spec-v5.6.md)
- [authorization-matrix-v5.6.md](/home/jolulop/code/TS-MS/docs/authorization-matrix-v5.6.md)
- [business-rules-catalog-v5.6.md](/home/jolulop/code/TS-MS/docs/business-rules-catalog-v5.6.md)
- [use-cases-acceptance-v5.6.md](/home/jolulop/code/TS-MS/docs/use-cases-acceptance-v5.6.md)
- [non-functional-requirements-v5.6.md](/home/jolulop/code/TS-MS/docs/non-functional-requirements-v5.6.md)
- [data-model-erd-v5.6.md](/home/jolulop/code/TS-MS/docs/data-model-erd-v5.6.md)
- [database-schema-diagram.md](/home/jolulop/code/TS-MS/docs/database-schema-diagram.md)

## Version Notes

v5.6 captures these major implemented changes relative to the older baseline docs:
- Country was renamed to Office.
- Office-level configuration replaced Business Unit-owned configuration.
- Office creation now bootstraps an initial Business Unit and Office admin employee.
- Clients and Cost Centers are now Office-level masters.
- Pricing Models were added as a new Office-level master.
- Projects now require a Pricing Model.
- System Management now includes Office, Project, Project Assignment, Calendar, Calendar Special Day, Calendar Period Rule, and Pricing Model management.
- Office Management now uses a standalone Office create screen, header-level status filters, and active-employee counts in the collection grid.
- Yearly Calendars are Office-level and shared by all Business Units in the Office.
- Calendar Period Rules remain Business Unit-specific inside the shared Office calendar and may overlap across different Business Units.
- Calendar Period Rules can enable working Saturdays and Sundays with explicit weekend max-hours.
- Guarded delete actions exist on selected System Management detail screens.
- Live Project Management is available in `TS/Project Management` for
  `TS_ADMIN`, `PROJECT_OWNER`, and `PROJECT_MANAGER`.
- Live Project Time Inquiry is available to Project Owners and Project Managers.
- System Management edit screens now follow a consistent standalone create/edit layout with bottom delete actions.
- The authenticated left navigation is organized into `My info`, `TS/Project Management`, and `System Management`.
- Basic `USER`-only sessions skip the dashboard, reports hub, and the entire
  `TS/Project Management` navigation group.
- `My Timesheets` and `My History` are consolidated into one personal weekly list, and the legacy history route redirects there.
- `My Timesheets` shows synthetic `Missing` rows for weekly gaps since employee record creation.
- `My Timesheets` now owns the personal `Status` and week-start filter panel that
  previously lived under the personal history report.
- System Management collections use the first-column item link as the visible navigation path and keep the old action column hidden.
- The missing-timesheets report is now project-scoped for `PROJECT_OWNER`, `PROJECT_MANAGER`, and `TS_ADMIN`, with CSV export in UI and API.
- `PROJECT_OWNER` can now manage owned projects and owned-project assignments from System Management.
- `PROJECT_MANAGER` can now manage assignments for managed projects from System Management.

## Reading Order

1. Functional specification
2. Authorization matrix
3. Business rules catalog
4. UI screen specification
5. Integration API specification
6. Use cases and acceptance
7. Data model and schema diagram
8. Non-functional requirements
