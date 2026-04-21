# Phase 1 Foundation and Tooling

## 1. Goal

Establish a minimal, reliable engineering foundation for local-first development that can later be ported to Azure with low friction. Phase 1 stops before core business workflows and focuses on stack choice, repo scaffolding, developer tooling, CI, documentation, and a repeatable reference-data strategy.

## 2. Scope

In scope:
- Choose the implementation stack for local development and later Azure deployment.
- Scaffold the repository into a runnable application baseline.
- Configure formatter, linter, test runner, and local quality commands.
- Configure CI to validate install, lint, tests, and basic app bootstrapping.
- Add core developer and architecture documentation.
- Define and implement the Phase 1 seed/reference-data strategy.
- Add minimal smoke functionality proving the scaffold works locally:
  - app boots
  - health endpoint works
  - test suite runs
  - seed/reference-data command runs

Out of scope:
- Authentication and session flow implementation.
- Authorization policy enforcement.
- Business Unit, employee, project, calendar, charge code, and timesheet business features.
- Approval workflow.
- Reporting, archive/restore, import/export, reopen, reminders, timer support, leave integration, and custom work attributes.
- Full domain schema for transactional TS behavior.

## 3. Source documents

- docs/TS MAnagement functional specification v.5.1.docx
- docs/Business Rules Catalog v5.1.docx
- docs/Non-Functional Business Requirements  v5.1.docx
- docs/Data Model - ERD v5.1.docx
- AGENTS.md
- PLANS.md
- README.md

Only the architecture-relevant portions of the product specs govern this phase, because Phase 1 does not yet implement business workflows.

## 4. Current state

- The repository currently contains planning and specification documents only.
- `README.md` already points toward a Python/Django local-first approach targeting Azure later.
- No application code, CI, formatter, linter, tests, seed mechanism, or runnable scaffold is present.
- The previous Phase 1 plan was too broad and pulled in submit/approval workflow scope too early.

## 5. Target behavior

After Phase 1:
- A new developer can clone the repo, create the local environment, install dependencies, and run the app in WSL with a short documented setup flow.
- The repository has a clear, opinionated stack aligned with local development first and Azure later.
- The repo contains a runnable scaffold with a health check and placeholder app shell.
- Formatting, linting, and tests run consistently through standard commands.
- CI runs automatically and blocks obvious regressions in setup and basic quality gates.
- Documentation explains the chosen stack, local development flow, repo layout, CI expectations, and reference-data strategy.
- Reference data needed by future phases has a versioned, idempotent seeding approach distinct from optional sample/demo data.

### Chosen stack

- Language/runtime: Python 3.12
- Application framework: Django monolith
- UI approach: server-rendered Django templates with lightweight progressive enhancement; no separate SPA in Phase 1
- Database: PostgreSQL as the primary database from the start for local, CI, and Azure parity
- Local infrastructure: WSL-based development with a lightweight local PostgreSQL dependency
- Packaging/config: `pyproject.toml`-based project configuration
- Formatter/linter: Ruff
- Test runner: pytest with `pytest-django`
- CI: GitHub Actions

Rationale:
- Django gives the fastest path to a working local-first enterprise CRUD foundation without splitting frontend/backend concerns too early.
- PostgreSQL from the beginning reduces “works locally, breaks on Azure” drift.
- Ruff and pytest keep the toolchain small and fast.
- GitHub Actions is the simplest default CI choice for repository-level automation.

## 6. Affected areas

Repository structure:
- root project layout
- Python package and configuration files
- scripts and developer command entry points
- CI workflow files
- environment template files

Application scaffold:
- Django project package
- base app or core app
- settings modules
- URL routing
- health endpoint
- base template/layout

Quality/tooling:
- formatter and lint configuration
- test configuration
- coverage configuration if used
- pre-commit hooks if adopted in the scaffold

Documentation:
- root README
- architecture/stack documentation
- local setup guide
- contribution or developer workflow guide
- reference-data strategy documentation

Data/bootstrap:
- reference-data app or package
- seed manifests/files
- idempotent seed command

## 7. Business rules impacted

Phase 1 does not implement end-user business workflows, but the scaffold must preserve these future constraints:

- Internal authorization must later be based on TS employee data, not the external validation system.
- Role values must come from internal reference data.
- Status values must come from internal reference data.
- Auditability will be required for sensitive workflow actions in later phases.
- Row-level scope must be enforceable server-side in later phases.
- The data model will later need unique active employee email handling, weekly timesheet uniqueness, charging-target xor rules, and approval-history preservation.

Implication for Phase 1:
- avoid scaffold choices that make internal auth, scoped queries, audit logging, or reference-data seeding awkward later
- seed reference codes in a way that can become production-safe system data

## 8. Authorization impact

Roles affected:
- none in runtime behavior yet

Scope impact:
- no user-facing authorization is implemented in Phase 1

Design constraints to preserve:
- role constants should live in one reference-data source, not scattered through code
- app structure should allow centralized policy helpers in Phase 2+
- template/navigation scaffolding should anticipate `System Management` and `TS Management` blocks without implementing role-based visibility yet

## 9. Data model changes

- migration needed: yes, but only for minimal framework/bootstrap needs
- tables affected:
  - Django framework tables
  - optional minimal `reference_data` table(s) if implemented in Phase 1
- constraints affected:
  - stable unique code strategy for reference values
  - safe upsert key strategy for seeded records
- reference data seed changes:
  - baseline role codes
  - baseline status codes that are clearly defined in the specs
- backfill needed: no

Recommended seed strategy:
- separate schema migrations from seed execution
- store reference definitions in version-controlled files or code-owned manifests
- seed by stable business code, not by display label
- make seeding idempotent
- separate mandatory reference data from optional local demo/sample data
- provide one command for mandatory system/reference data and a different command for sample dev data if sample data is later added

## 10. API changes

Endpoints to add/change:
- health/readiness endpoint

Request/response changes:
- minimal structured health response suitable for local smoke checks and future Azure probes

Error codes:
- not a focus in Phase 1 beyond basic framework-safe error handling

OpenAPI updates required:
- no

## 11. UI changes

Screens to add/change:
- minimal home/landing page
- base layout shell for future navigation
- error pages only if included in the scaffold

New actions:
- none beyond proving the scaffold renders

Validation messages:
- not a focus in Phase 1

Role visibility changes:
- none yet

## 12. Audit and logging impact

Audit events to add/update:
- none for business workflows in Phase 1

Operational logs/metrics:
- configure structured application logging baseline
- document where future audit logging will fit
- make health checks observable in local and CI runs

## 13. Implementation steps

1. Phase 1A: confirm and document the stack choice.
   - Record the chosen stack and rationale in the main docs.
   - Align the repo guidance around one implementation direction.
2. Phase 1B: scaffold the repo.
   - Create the Django project structure, app shell, settings, URLs, health endpoint, and base template.
   - Add environment configuration files and local setup conventions for WSL.
3. Phase 1C: configure local quality tooling.
   - Add Ruff configuration for formatting and linting.
   - Add pytest and `pytest-django` configuration.
   - Define standard commands for format, lint, test, and runserver.
4. Phase 1D: configure CI.
   - Add a GitHub Actions workflow.
   - Run install, lint, tests, and basic app startup/smoke verification.
   - Use PostgreSQL in CI to match the chosen local/Azure path.
5. Phase 1E: add foundational docs.
   - Update `README.md`.
   - Add architecture, local setup, and developer workflow docs.
   - Add a reference-data strategy document.
6. Phase 1F: implement the seed/reference-data baseline.
   - Create the initial reference-data structure and seed command.
   - Seed stable role/status codes required by later phases.
   - Verify idempotent seed behavior in local and CI execution.

## 14. Test plan

Unit tests:
- health endpoint response test
- seed command test
- configuration smoke tests for settings import and URL resolution

Integration tests:
- app boots against PostgreSQL test database
- seed command can run repeatedly without duplicating reference values

E2E tests:
- not required in Phase 1

Manual verification:
- local setup instructions work on WSL from a clean clone
- app starts locally
- health endpoint responds successfully
- lint and test commands complete successfully
- CI passes on a clean branch

## 15. Risks and mitigations

- Risk: introducing business workflows in Phase 1 before the foundation is stable.
  - Mitigation: keep scope limited to scaffolding, tooling, docs, and seed strategy.
- Risk: choosing SQLite locally and PostgreSQL later creates avoidable behavior drift.
  - Mitigation: use PostgreSQL as the primary database from the start.
- Risk: overloading the repo with too many tools before the team gets value.
  - Mitigation: keep the toolchain intentionally small: Django, Ruff, pytest, GitHub Actions.
- Risk: mixing mandatory reference data with throwaway demo data.
  - Mitigation: define separate commands and storage conventions for reference seeds versus sample data.
- Risk: Azure deployment later requires rework because local settings were too ad hoc.
  - Mitigation: use environment-based Django settings and health/readiness patterns compatible with Azure hosting.

## 16. Rollout / deployment notes

- feature flag needed: no
- migration sequencing:
  - framework/bootstrap migration first
  - optional reference-data migration next
- seed sequencing:
  - run mandatory reference-data seed after migrations
- backward compatibility considerations:
  - none yet because no existing application runtime is present
- Azure readiness notes:
  - prefer env-driven configuration
  - keep static-file and health-check setup Azure-compatible
  - avoid local-only assumptions in paths, services, or commands

## 17. Open questions / assumptions

- Assumption: Phase 1 is intentionally a foundation phase, not a business-feature phase.
- Assumption: local-first and Azure-later is best served by a Django monolith with PostgreSQL from day one.
- Assumption: GitHub Actions is the CI platform unless the repository hosting context later dictates otherwise.
- Open question: whether sample/demo data should be created in Phase 1 or deferred until the first business workflow phase. The safer narrow choice is to defer demo data and seed only mandatory reference data now.

## 18. Definition of done

- stack choice documented
- repo scaffold created
- formatter configured
- linter configured
- test runner configured
- CI workflow configured
- README and supporting developer docs updated
- reference-data strategy documented
- seed/reference-data baseline implemented and verified as idempotent
- local smoke run and CI verification completed
