# Specification Index v5.9

## Purpose

This markdown set is the current repository-aligned specification for the implemented Timesheet Management System as of `2026-05-19`.

It supersedes the incremental markdown delta notes in:
- `docs/functional-spec-v5.2.md`
- `docs/ui-screen-spec-v5.2.md`
- `docs/integration-api-spec-v5.2.md`

It also provides a code-aligned working reference alongside the legacy `.docx` documents in this folder.

## v5.9 Documents

- [functional-spec-v5.9.md](/home/jolulop/code/TS-MS/docs/functional-spec-v5.9.md)
- [ui-screen-spec-v5.9.md](/home/jolulop/code/TS-MS/docs/ui-screen-spec-v5.9.md)
- [integration-api-spec-v5.9.md](/home/jolulop/code/TS-MS/docs/integration-api-spec-v5.9.md)
- [authorization-matrix-v5.9.md](/home/jolulop/code/TS-MS/docs/authorization-matrix-v5.9.md)
- [business-rules-catalog-v5.9.md](/home/jolulop/code/TS-MS/docs/business-rules-catalog-v5.9.md)
- [use-cases-acceptance-v5.9.md](/home/jolulop/code/TS-MS/docs/use-cases-acceptance-v5.9.md)
- [non-functional-requirements-v5.9.md](/home/jolulop/code/TS-MS/docs/non-functional-requirements-v5.9.md)
- [data-model-erd-v5.9.md](/home/jolulop/code/TS-MS/docs/data-model-erd-v5.9.md)
- [database-schema-diagram.md](/home/jolulop/code/TS-MS/docs/database-schema-diagram.md)

## Version Notes

v5.9 captures these major implemented changes relative to the older baseline docs:
- Country was renamed to Office.
- Office-level configuration replaced Business Unit-owned configuration.
- Office creation now bootstraps an initial Business Unit and Office admin employee.
- Clients and Cost Centers are now Office-level masters.
- Pricing Models were added as a new Office-level master.
- Projects now require a Pricing Model.
- System Management now includes Office, Project, Project Assignment, Calendar, Calendar Special Day, Calendar Period Rule, and Pricing Model management.
- System Management now includes a master-only Employee Transfer workflow for
  safe cross-Office employee moves.
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
- The existing report viewer now supports CSV export across the current operational report slices in the HTML UI, while Missing Timesheets by Project keeps the additional `/api/v1` export flow.
- `PROJECT_OWNER` can now manage owned projects and owned-project assignments from System Management.
- `PROJECT_MANAGER` can now manage assignments for managed projects from System Management.
- `TS_ADMIN` now has approval oversight visibility without gaining approval authority from the admin role alone.
- related timesheet detail exposes existing admin exception actions in the HTML UI.
- timesheet detail shows short-date submission and approval metadata.
- `Enable Copy Previous Week` is now a real Office-controlled user action on
  `My Timesheets`; `Timer` and `Leave Integration` remain inactive.
- advanced TS Admin analytics reports now include Employee Utilization,
  Office / BU Time Summary, General Charge Code Usage, and Approval Turnaround
  with CSV export.
- Country and Office administration now have documented JSON admin API parity,
  including guarded `DELETE` behavior.
- General Charge Code approval routing now exposes richer governance visibility,
  stronger ad-hoc role validation, and detail-screen routing/coverage sections.

## Reading Order

1. Functional specification
2. Authorization matrix
3. Business rules catalog
4. UI screen specification
5. Integration API specification
6. Use cases and acceptance
7. Data model and schema diagram
8. Non-functional requirements
