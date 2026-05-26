# Specification Index v8.0

## Purpose

This markdown set is the current approved v8.0 source-of-truth specification
for the Timesheet Management System as of `2026-05-26`.

It supersedes the incremental markdown delta notes in:
- `docs/functional-spec-v5.2.md`
- `docs/ui-screen-spec-v5.2.md`
- `docs/integration-api-spec-v5.2.md`

It also provides a code-aligned working reference alongside the legacy `.docx` documents in this folder.

## v8.0 Documents

- [functional-spec-v8.0.md](/home/jolulop/code/TS-MS/docs/functional-spec-v8.0.md)
- [ui-screen-spec-v8.0.md](/home/jolulop/code/TS-MS/docs/ui-screen-spec-v8.0.md)
- [integration-api-spec-v8.0.md](/home/jolulop/code/TS-MS/docs/integration-api-spec-v8.0.md)
- [authorization-matrix-v8.0.md](/home/jolulop/code/TS-MS/docs/authorization-matrix-v8.0.md)
- [business-rules-catalog-v8.0.md](/home/jolulop/code/TS-MS/docs/business-rules-catalog-v8.0.md)
- [use-cases-acceptance-v8.0.md](/home/jolulop/code/TS-MS/docs/use-cases-acceptance-v8.0.md)
- [non-functional-requirements-v8.0.md](/home/jolulop/code/TS-MS/docs/non-functional-requirements-v8.0.md)
- [data-model-erd-v8.0.md](/home/jolulop/code/TS-MS/docs/data-model-erd-v8.0.md)
- [database-schema-diagram.md](/home/jolulop/code/TS-MS/docs/database-schema-diagram.md)

## Version Notes

v8.0 promotes the current code-aligned source-of-truth set and adds these
clarifications relative to v7.1:
- KAN-105 Milestone 1 has a working isolated Azure development instance at
  `https://app-tsms-dev.azurewebsites.net`.
- KAN-117 through KAN-120 are represented by the Azure DevOps foundation,
  runtime readiness, hardened App Service configuration, and Google SSO
  trusted-header browser bootstrap.
- KAN-121 Phase 5 is represented by a deployed Django package, App Service
  startup command, Azure PostgreSQL migration run, and idempotent reference/dev
  seed execution.
- Azure dev runs with `TSMS_ENVIRONMENT=production`, Google SSO through App
  Service Authentication, Key Vault-backed secrets, and PostgreSQL rather than
  SQLite.
- Azure App Service / Oryx dependency detection is supported by the repository
  `requirements.txt` file.
- PostgreSQL migration compatibility for the historical Country-to-Office
  migration is documented: existing `country_*` indexes on the renamed `office`
  table are normalized before recreating the standalone `country` table, and
  the Office sequence is reset after explicit-id seed history.
- The first deployed browser SSO smoke and the Azure PostgreSQL migration/seed
  checks were completed on 2026-05-26.

The v8.0 baseline also carries forward these major approved behaviors from
the older docs:
- documented `/api/v1/admin` guarded `DELETE` routes are JSON endpoints; the
  explicit non-endpoint list now contains only UI-only flows
- Project Assignment create behavior is documented and tested so normal
  assignment writes reject employees who are not active in the selected
  project's Business Unit
- the standard repository lint and format gates are clean for the promoted
  baseline
- Country was renamed to Office.
- Office-level configuration replaced Business Unit-owned configuration.
- Office creation now bootstraps an initial Business Unit and Office admin employee.
- Clients and Cost Centers are now Office-level masters.
- Pricing Models were added as a new Office-level master.
- Projects now require a Pricing Model.
- System Management now includes Office, Project, Project Assignment,
  Cross-Office Staffing, Calendar, Calendar Special Day, Calendar Period Rule,
  and Pricing Model management.
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
- The existing `/api/v1/admin` master-data surface now exposes guarded
  `DELETE` parity for the current CRUD-supported entities that already have
  service-layer safe-delete rules.
- Employee administration now has JSON API parity for collection list, detail,
  guarded delete, create, update, role replacement, and Business Unit scope
  replacement; employee transfer remains a UI-only workflow.
- General Charge Code approval routing now exposes richer governance visibility,
  stronger ad-hoc role validation, and detail-screen routing/coverage sections.
- System Management collections and detail screens now use a more consistent
  standalone create, inline-filter, and bottom guarded-delete presentation
  pattern, including Country Management parity with the rest of the admin shell.
- Employee detail now shows a read-only active project-assignment grid with
  direct project links.
- Project Assignment Management now shows Client and Project Name columns plus
  dependent Client and Project filters.
- Project Management now shows BU names, Client, owner and manager full names,
  employee assignment counts, an inline Client filter that preserves status
  selection, and a pending-approval drill-down into the Approval Worklist.
- TS/Project Management navigation now places `Approval Worklist` above
  `Reports`.
- Shared report-viewer screens now use the stacked top filter/totals layout,
  and Reports Hub keeps `Archived Timesheets`, `Audit History`, and
  `Integration Jobs` at the bottom of the admin card list.
- Client Management now shows one row per Business Unit with active client
  projects and routes project-count clicks through Business Unit-aware
  authorization checks.
- v8.0 includes the dedicated `Cross-Office Staffing` model alongside
  normal `Project Assignments`.
- Cross-office staffed employees keep home-office calendar, calendar period
  rule, and General Charge Code semantics.
- Employee-management flows and compatibility backfill now ensure an assigned
  Office calendar exists when one is available, and may clone a single Office
  calendar rule pattern into the employee's primary Business Unit to keep time
  entry operable.
- Cross-office staffing create UX now keeps target-project context visible and
  narrows origin-office employee selection live from the chosen Origin Office.
- Origin-office employee detail keeps cross-office staffed projects visible as
  read-only rows, and Office / BU Time Summary now groups project-charged
  hours by project while keeping cross-office visibility available from both
  the home-office and target-office sides and displaying the charged project's
  Office / BU on those rows.
- Office / BU Time Summary Business Unit filtering is a scoped perspective
  filter: in-scope selected BUs include rows matching either the
  weekly-timesheet home BU or the charged target project BU, while out-of-scope
  filter values must not widen access.
- Approval workspace polish now uses a shared `Approval Worklist` title for
  approvers and `TS_ADMIN`, shortens employee/approver labels to names in the
  grids and detail context, adds TS submission date visibility, and stacks the
  detail context above the related links box.
- Project Time now uses a single grouped results grid with BU/project summary
  rows, nested week summary rows, and expand/collapse detail visibility while
  CSV export stays flat, and Pending Approvals now starts with Week Start Date
  while dropping the
  internal Approval Item and Status columns from the report output.
- Project approval and project-time visibility follow the target project even
  when the charged employee belongs to another Office.
- For `TS_ADMIN`, Project Time Business Unit filtering follows the charged
  target project's Business Unit while the displayed `BU` value remains the
  weekly-timesheet home Business Unit.
- Approved Phase 3 scope moves project approval oversight for `TS_ADMIN` to
  the target project Office and scoped target Business Unit side while keeping
  Office / BU summary analytics on the weekly-timesheet home-BU side unless
  later changed.
- Personal timesheet deletion remains audit-guarded: `CREATED` status alone is
  not enough when prior submission history exists.
- Authentication now has an explicit provider boundary: local
  `development-email` access is disabled in production mode, while the
  `trusted-header` contract supports Google SSO / Azure ingress by accepting a
  trusted email claim before internal TS role and scope resolution.
- Production settings now fail fast for unsafe secrets, missing allowed hosts,
  non-PostgreSQL production databases, development auth, and insecure
  HTTPS/cookie settings; Azure deployment variables are documented in
  `docs/deployment/azure-production-checklist.md`.
- Office and Business Unit configuration screens now present reserved
  compatibility settings in a muted disabled state: `Timesheet Cutoff Date`,
  `Count Non-billable In Daily Limit`, `Enable Timer`, and
  `Enable Leave Integration` remain in the data model but are not editable from
  those HTML screens.
- Approval Mode configuration exposes only the implemented `PROJECT` mode in
  the Office HTML UI; legacy `LINE` and `MIXED` reference values remain hidden
  compatibility values.
- Daily limit validation always counts all charged time, including billable and
  non-billable lines; the legacy non-billable switch is retained only for
  compatibility.
- Normal Project Assignment employee selection is limited to the active user's
  Business Unit scope, and writes reject employees who are not active in the
  selected project's Business Unit. Cross-office staffing remains the dedicated
  path for employees outside the target project Office / BU.

## Reading Order

1. Functional specification
2. Authorization matrix
3. Business rules catalog
4. UI screen specification
5. Integration API specification
6. Use cases and acceptance
7. Data model and schema diagram
8. Non-functional requirements
