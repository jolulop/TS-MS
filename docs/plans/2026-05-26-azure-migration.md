# Azure Migration Plan

Status: proposed
Date: 2026-05-26
Branch: `KAN-51-move-to-azure`
Worktree: `/home/jolulop/code/TS-MS.worktrees/KAN-51-move-to-azure`

## Goal

Deploy the current Timesheet Management System to Azure with the existing
server-rendered web interface, `/api/v1` JSON API, reporting, audit behavior,
and automated tests intact.

The first Azure release must support:

- VS Code development against Azure Repos.
- Three isolated environments: development, testing, and production.
- A working Azure development instance as the first implementation milestone.
- Google SSO at the ingress boundary.
- HTTPS-only access.
- PostgreSQL-backed production data.
- Automated build, test, deploy, smoke, and readiness checks.
- A path for a future MCP server without implementing MCP in this phase.
- Weekly peaks of about 50 concurrent users.

## Non-Goals

- Rewriting the Django monolith as a SPA or microservice system.
- Implementing the future MCP server now.
- Moving reports to an asynchronous reporting engine unless load testing proves
  it is needed.
- Active-active multi-region production in the first Azure release.

## Current Architecture Assessment

The current app is a good fit for Azure App Service as a first production
target:

- Python 3.12 Django monolith.
- Server-rendered templates plus JSON endpoints under `/api/v1`.
- Local SQLite bootstrap, with PostgreSQL already supported through
  `TSMS_DB_BACKEND=postgres`.
- Production validation already fails closed for unsafe settings when
  `TSMS_ENVIRONMENT=production`.
- Auth already has the required production boundary shape:
  `TSMS_AUTH_PROVIDER=trusted-header` and
  `TSMS_TRUSTED_EMAIL_HEADER=HTTP_X_MS_CLIENT_PRINCIPAL_NAME`.
- Internal TS roles, Office scope, BU scope, owner scope, and manager scope stay
  inside application data after external email validation.
- JSON logging already exists for production ingestion.
- `/health/` exists, currently as a lightweight liveness endpoint.

Main migration gaps:

- No Azure infrastructure-as-code yet.
- No Azure pipeline yet.
- No production WSGI server dependency is declared.
- No production static-file strategy is declared.
- Browser SSO needs a production session bootstrap path from trusted ingress
  headers; the current home page still presents the local development email form
  when no internal TS session exists.
- `/api/v1` needs a precise supported API authentication contract under Google
  SSO.
- PostgreSQL TLS and connection lifetime settings should be explicit.
- Automated tests need a PostgreSQL parity lane because SQLite does not prove
  row-lock behavior.
- Azure readiness, smoke, and load checks are not yet automated.

## Delivery Strategy

Use a dev-first vertical slice. The phases below are workstreams and readiness
gates, not a strict waterfall. The first implementation target is a working
Azure development instance that proves the complete route from Azure Repos to a
running Django app on Azure with Google SSO, PostgreSQL, migrations, seed data,
basic web UI, basic `/api/v1` access, and one report smoke test.

After the development instance works, harden the same architecture for testing,
then promote to production only after parity tests, load tests, security checks,
and go-live readiness pass.

### Milestone 1: Working Azure Development Instance

Minimum scope:

- Azure Repos is connected and usable from VS Code.
- A pipeline skeleton can build and test the app.
- Dev resource group exists.
- Dev App Service for Linux exists.
- Dev Azure Database for PostgreSQL Flexible Server exists.
- Dev Key Vault exists and secrets are referenced by App Service settings.
- Dev Application Insights and Log Analytics are connected.
- Django runs on App Service with `DEBUG=0`.
- Static files render correctly.
- Google SSO authenticates a dev user through Azure ingress.
- Trusted-header session bootstrap initializes the internal TS session.
- Migrations run successfully against dev PostgreSQL.
- Reference seed data is loaded.
- Optional dev sample data is loaded only in the dev environment.
- Smoke test covers login, dashboard/profile, one timesheet path, one
  `/api/v1` endpoint, and one report page or CSV export.

Out of scope for Milestone 1:

- Production-grade HA.
- Full load testing.
- Production custom domain cutover.
- Full API client publishing guidance.
- MCP implementation.

Milestone 1 is complete when a developer can open the Azure dev URL, sign in
with Google, use the core UI, call a representative API endpoint, and confirm
the app is using Azure PostgreSQL rather than SQLite.

Use `docs/deployment/azure-development-checklist.md` as the operational
checklist for this milestone. Use
`docs/plans/2026-05-26-azure-open-decisions.md` to confirm the subscription,
region, naming, networking, Google SSO, Azure DevOps, and seed-data choices
before creating resources.

## Target Azure Blueprint

Recommended baseline:

```text
Developers
  -> VS Code
  -> Azure Repos
  -> Azure Pipelines
  -> Azure App Service per environment

Users and API clients
  -> HTTPS custom domain or azurewebsites.net
  -> Azure App Service Authentication with Google provider
  -> trusted email header
  -> Django internal session and authorization
  -> Azure Database for PostgreSQL Flexible Server

Operations
  -> Key Vault references for secrets
  -> Managed identity for secret access
  -> Application Insights and Log Analytics
  -> Azure Load Testing for weekly peak validation
```

### Core Azure Components

| Concern | Azure component | Direction |
| --- | --- | --- |
| Source control | Azure Repos Git | Use Azure DevOps project and branch policies. Developers clone/work from VS Code. |
| CI/CD | Azure Pipelines YAML | Run lint, tests, PostgreSQL parity tests, package, deploy, migrate, smoke. |
| Web/API hosting | Azure App Service for Linux | Best first fit for the Django monolith. Use Python 3.12, Gunicorn, HTTPS-only, health check. |
| Database | Azure Database for PostgreSQL Flexible Server | Replace SQLite in all Azure environments. Use General Purpose for production. |
| Secrets | Azure Key Vault | Store Django secret key, database password, Google provider secret, and future integration secrets. Use App Service Key Vault references. |
| Identity ingress | App Service Authentication, Google provider | Azure authenticates with Google and injects trusted identity headers. Django maps email to internal employee and roles. |
| TLS | App Service default cert plus custom domain certificate | Start with `*.azurewebsites.net`; bind a managed or owned cert for production domain. |
| Networking | VNet integration and private endpoints | Use private PostgreSQL access for test/prod. Prefer the same pattern for dev if budget allows. |
| Observability | Application Insights plus Log Analytics | Capture requests, traces, dependency metrics, stdout/stderr JSON logs, alerts. |
| Performance validation | Azure Load Testing | Validate 50 concurrent users with submit, approval, dashboard, and report journeys. |
| Persistent files | Azure Storage, optional for phase 1 | Not required for current CSV-in-response reporting. Add if future exports/media need durable files. |
| Future MCP | Separate service behind OAuth-aware ingress | Reserve API/auth design so MCP can be added later without weakening browser auth. |

## Environment Layout

Use separate resource groups and separate secrets per environment. Do not share
Google app registrations or Key Vaults between environments.

### Development

Purpose: cloud development integration and first deploy target.

Suggested resources:

- `rg-tsms-dev`
- `app-tsms-dev`
- `plan-tsms-dev`
- `pg-tsms-dev`
- `kv-tsms-dev`
- `appi-tsms-dev`
- `log-tsms-dev`

Sizing:

- App Service Basic or Standard tier is enough initially.
- PostgreSQL Burstable is acceptable only for dev cost control.
- No HA.
- Backup retention can remain low, for example 7 days.

Security posture:

- Still use Google SSO.
- Still use PostgreSQL.
- Still disable local `validated_email` login in Azure.
- Use dev-only employee data.

### Testing

Purpose: production-parity validation and UAT.

Suggested resources:

- `rg-tsms-test`
- `app-tsms-test`
- `plan-tsms-test`
- `pg-tsms-test`
- `kv-tsms-test`
- `appi-tsms-test`
- `log-tsms-test`

Sizing:

- App Service Standard or small Premium tier.
- PostgreSQL Flexible Server General Purpose, 2 vCores as the initial test
  baseline.
- No HA initially unless testing failover behavior.
- Backup retention 7 to 14 days.

Security posture:

- Same SSO, HTTPS, Key Vault, trusted-header, and dev-auth-disabled settings as
  production.
- Run full smoke, regression, and load tests before production promotion.

### Production

Purpose: real business use.

Suggested resources:

- `rg-tsms-prod`
- `app-tsms-prod`
- `plan-tsms-prod`
- `pg-tsms-prod`
- `kv-tsms-prod`
- `appi-tsms-prod`
- `log-tsms-prod`
- Optional `stg-tsms-prod` storage account for future durable exports/backups.

Initial sizing for 50 concurrent weekly users:

- App Service: start with a small Premium tier or equivalent production-capable
  tier, one always-on instance, and capacity to scale to two instances around
  weekly peaks.
- Gunicorn: start conservatively, then tune from load tests. A reasonable first
  shape is 2 to 4 workers with 2 threads each, depending on the selected App
  Service CPU and memory.
- PostgreSQL: General Purpose, 2 vCores, 8 GiB memory class or equivalent,
  64 GiB storage minimum, with headroom monitored through CPU, memory, IOPS,
  connections, locks, and slow queries.
- Enable PostgreSQL zone-redundant HA if the business requires higher
  availability than a single database node. Do not use Burstable for production.
- Backup retention: 35 days if business policy permits, otherwise document the
  selected retention and recovery objective.

Scale plan:

- Start with one app instance after successful load testing.
- Configure schedule or metric based scale-out to two instances during the
  weekly timesheet peak if CPU, response time, or queueing needs it.
- Keep Django session storage database-backed so multiple app instances remain
  stateless.
- Avoid writing user-generated files to the App Service local filesystem.

## Production App Settings

Each Azure app should set these values through App Service app settings, with
secret values coming from Key Vault references:

```text
TSMS_ENVIRONMENT=production
TSMS_DEBUG=0
TSMS_SECRET_KEY=@Microsoft.KeyVault(...)
TSMS_ALLOWED_HOSTS=<app>.azurewebsites.net,<custom-domain>
TSMS_CSRF_TRUSTED_ORIGINS=https://<app>.azurewebsites.net,https://<custom-domain>
TSMS_AUTH_PROVIDER=trusted-header
TSMS_ENABLE_DEV_AUTH=0
TSMS_TRUSTED_EMAIL_HEADER=HTTP_X_MS_CLIENT_PRINCIPAL_NAME

TSMS_DB_BACKEND=postgres
TSMS_DB_NAME=<database>
TSMS_DB_USER=<user>
TSMS_DB_PASSWORD=@Microsoft.KeyVault(...)
TSMS_DB_HOST=<postgres-host>
TSMS_DB_PORT=5432

TSMS_SESSION_COOKIE_SECURE=1
TSMS_CSRF_COOKIE_SECURE=1
TSMS_SECURE_SSL_REDIRECT=1
TSMS_ENABLE_PROXY_SSL_HEADER=1
TSMS_SECURE_PROXY_SSL_HEADER_NAME=HTTP_X_FORWARDED_PROTO
TSMS_SECURE_PROXY_SSL_HEADER_VALUE=https

TSMS_LOG_FORMAT=json
TSMS_LOG_LEVEL=INFO
TSMS_OBSERVABILITY_LOG_LEVEL=INFO
APPLICATIONINSIGHTS_CONNECTION_STRING=<App Insights connection string>
```

For test and cloud development, either use the same hardened production setting
set with environment-specific hosts and secrets, or add a code-supported
`TSMS_CLOUD_HARDENING=1` style validation switch so non-production Azure
environments also fail closed.

## Google SSO Design

Use Azure App Service Authentication with the Google provider.

Ingress responsibilities:

- Redirect unauthenticated browser requests to Google.
- Validate Google authentication.
- Forward only platform-injected identity headers to Django.
- Use the App Service header `X-MS-CLIENT-PRINCIPAL-NAME`, exposed to Django as
  `HTTP_X_MS_CLIENT_PRINCIPAL_NAME`.

Django responsibilities:

- Never trust a browser-posted email in Azure.
- Read the trusted header only after Azure ingress authentication.
- Canonicalize email.
- Resolve the active internal employee.
- Resolve internal roles, Office, and BU scope from TS data only.
- Deny by default if the employee is inactive, missing, duplicated, or lacks an
  active role.

Required code adaptation:

- Add an idempotent trusted-header session bootstrap path for production
  browser entry. When `TSMS_AUTH_PROVIDER=trusted-header`, a first authenticated
  GET to `/` should initialize the internal TS session from the trusted header
  and redirect to the normal dashboard or TS landing page.
- Keep the local access-entry form available only when the development email
  adapter is enabled.
- Add tests proving production does not accept posted `validated_email` values.
- Add tests proving trusted headers initialize sessions and missing headers deny
  access.

API access decision:

- Human/API calls can use the App Service authenticated session cookie after
  Google sign-in.
- Browserless clients should use App Service's token validation flow or a later
  dedicated API ingress pattern. This needs a deliberate acceptance test before
  publishing API client instructions.
- Do not add anonymous API access.
- Do not bypass internal TS authorization. App Service authentication proves
  external identity only; TS still decides data access.

## Future MCP Architectural Requirement

Do not implement MCP in this migration, but keep these constraints:

- Keep `/api/v1` authorization explicit and testable.
- Avoid coupling all future API access to browser-only cookie flows.
- Prefer a later separate MCP service hosted in Azure Container Apps or another
  App Service, protected by OAuth-aware ingress and connected only to approved
  TS service APIs.
- If App Service Authentication is still the ingress, track the Azure protected
  resource metadata support because it is relevant to MCP authorization, but do
  not depend on preview-only behavior for production until it is stable.

## Deployment Readiness Plan

### Phase 1: Azure DevOps Foundation

Deliverables:

- Azure DevOps project.
- Azure Repos Git repository.
- Branch policy for `main` and release branches:
  - PR required.
  - Pipeline required.
  - At least one reviewer.
  - No direct production commits.
- VS Code setup instructions:
  - Clone from Azure Repos.
  - Use Git Credential Manager or SSH.
  - Use the repository Makefile locally.
- Azure Pipelines service connection to the Azure subscription.

Readiness checks:

- Developer can clone, branch, commit, push, and open PR from VS Code.
- Pipeline runs on PR.
- Pipeline has no long-lived Azure credentials in source.

### Phase 2: Infrastructure as Code

Deliverables:

- `infra/` directory using Bicep unless a different IaC standard is chosen.
- Parameterized environment deployment for dev/test/prod.
- Resource groups, App Service plans, Web Apps, PostgreSQL servers, Key Vaults,
  managed identities, Application Insights, Log Analytics, VNet/private endpoint
  resources, and diagnostic settings.
- Output values for app URLs, host names, Key Vault names, and database hosts.

Readiness checks:

- Dev environment can be provisioned from scratch.
- Re-running IaC is idempotent.
- Secrets are stored in Key Vault, not source.
- App managed identity has only required Key Vault secret read access.

### Phase 3: Application Runtime Readiness

Deliverables:

- Add production runtime dependencies:
  - `gunicorn`
  - `whitenoise` or another explicit static-file strategy
  - optional Azure Monitor OpenTelemetry package
- Add startup command or startup script for App Service.
- Add `collectstatic` support in build or release flow.
- Add PostgreSQL TLS options and connection lifetime configuration.
- Add liveness/readiness endpoint split if needed:
  - liveness: process is up
  - readiness: database is reachable and migrations are applied

Readiness checks:

- App starts on App Service.
- Static CSS/assets render with `DEBUG=0`.
- `/health/` returns `200`.
- Readiness check fails when database is intentionally unreachable.
- `python manage.py check --deploy` is reviewed and either passes or has
  documented accepted warnings.

### Phase 4: Identity and Session Bootstrap

Deliverables:

- Google provider configured per environment.
- Separate Google OAuth client per environment.
- App Service Authentication enabled.
- Production browser entry initializes internal TS session from trusted header.
- Logout clears Django session and routes through App Service logout if needed.

Readiness checks:

- Unauthenticated user is redirected to Google.
- Authenticated Google user with matching active employee enters TS.
- Unknown Google email is denied and audited.
- Inactive employee is denied and audited.
- User with no internal role is denied and audited.
- Browser-posted `validated_email` is rejected in production.
- Header spoofing is not accepted except from Azure ingress.

### Phase 5: Database Migration and Seed Readiness

Deliverables:

- PostgreSQL database created per environment.
- Migrations run from an execution context that can reach private PostgreSQL:
  App Service SSH/Kudu for early dev, then automated release job or self-hosted
  Azure Pipelines agent inside the VNet for repeatable environments.
- Reference seed command run in each environment.
- Dev sample data remains dev-only.
- Production data migration decision recorded:
  - empty production launch with reference data only, or
  - migration from an existing source database/export.

Readiness checks:

- `python manage.py migrate` succeeds against Azure PostgreSQL.
- `python manage.py seed_reference_data` is idempotent.
- PostgreSQL row-lock behavior is verified for submit/approve/reopen/archive
  critical workflows.
- Backups and point-in-time restore are tested before go-live.

### Phase 6: CI/CD

Deliverables:

- PR pipeline:
  - create virtualenv
  - install package with dev dependencies
  - `make lint`
  - `make format-check`
  - `make test`
  - `make check`
- PostgreSQL parity test job:
  - run selected concurrency and migration-sensitive tests against PostgreSQL
  - include timesheet submit, approval, reopen, archive/restore, and calendar
    overlap flows
- Deployment pipeline:
  - deploy to dev automatically from integration branch
  - deploy to test after approval or release branch
  - deploy to production after test gates and manual approval
  - run migrations once per release
  - run smoke tests after deploy

Readiness checks:

- Failed test blocks deploy.
- Failed migration blocks promotion.
- Failed smoke test blocks production approval.
- Release artifacts are traceable to commit SHA.

### Phase 7: Reporting and API Validation

Deliverables:

- Smoke coverage for server-rendered report pages.
- Smoke coverage for CSV exports.
- API smoke scripts for:
  - session
  - employee/business-unit scope
  - representative admin endpoint
  - representative timesheet endpoint
  - representative report/export endpoint
- Query-count tests remain in the normal test suite.

Readiness checks:

- Reports respect Office/BU/project scope in Azure.
- CSV downloads work over HTTPS.
- API errors remain structured with stable business error codes.
- Unauthorized rows are not returned by API endpoints.

### Phase 8: Observability and Operations

Deliverables:

- Application Insights connected.
- Log Analytics workspace connected.
- Diagnostic settings for App Service and PostgreSQL.
- Alerts for:
  - App 5xx rate
  - high response time
  - app CPU/memory pressure
  - database CPU/memory/storage/IOPS pressure
  - database connection saturation
  - failed login/session initialization spikes
  - failed deployment
- Dashboard for weekly peak day.

Readiness checks:

- Application logs appear in Log Analytics.
- Request traces show web/API activity.
- PostgreSQL metrics are visible.
- Audit events remain queryable from the application database.
- Report export observability events are visible.

### Phase 9: Load, Security, and Go-Live

Deliverables:

- Azure Load Testing script or Locust/JMeter script for 50 concurrent users.
- Test journeys:
  - login/session initialization
  - view dashboard
  - create/save/submit timesheet
  - approval list/detail approve/reject
  - admin list/detail
  - representative reports and CSV export
- Security checklist:
  - HTTPS only
  - custom domain TLS bound
  - `DEBUG=0`
  - dev auth disabled
  - allowed hosts explicit
  - CSRF origins explicit
  - secure cookies
  - Key Vault references resolved
  - PostgreSQL public access disabled for test/prod if private endpoint is used
  - no secrets in repo or pipeline logs

Initial performance targets to validate and tune:

- 50 concurrent users for 30 minutes.
- Normal server-rendered pages p95 under 2 seconds.
- Save/submit p95 under 3 seconds.
- Standard reports p95 under 10 seconds.
- Error rate under 1 percent excluding intentional authorization denials.
- No database lock timeouts during concurrent submit/approval tests.

Go-live checks:

- Full regression green.
- PostgreSQL parity tests green.
- Test environment UAT signed off.
- Load test meets target or sizing is adjusted and retested.
- Backup restore tested.
- Rollback plan tested.
- Production Google OAuth redirect URIs verified.
- Production domain and certificate verified.

## Code Migration Plan

Recommended implementation order:

1. Runtime packaging
   - Add `gunicorn`.
   - Add a static-file serving strategy.
   - Add App Service startup command/script.
   - Add optional OpenTelemetry instrumentation behind environment settings.

2. Settings hardening
   - Add explicit PostgreSQL TLS configuration.
   - Add optional database connection lifetime environment setting.
   - Add hardened validation for cloud dev/test, not only production, if we keep
     separate non-production `TSMS_ENVIRONMENT` values.
   - Add deployment documentation for all app settings.

3. SSO session bootstrap
   - Add trusted-header auto-bootstrap for first browser entry.
   - Keep local email entry only for local development.
   - Add logout behavior compatible with App Service Authentication.
   - Add regression tests for Google/Azure ingress behavior.

4. Health and readiness
   - Keep a lightweight liveness endpoint.
   - Add database-aware readiness if needed by App Service health checks and
     post-deploy smoke tests.
   - Confirm health check works with App Service Authentication settings.

5. CI/CD and PostgreSQL parity
   - Add Azure Pipelines YAML.
   - Add PostgreSQL test lane.
   - Add focused concurrency tests where SQLite cannot prove behavior.
   - Add smoke scripts for deployed environments.

6. Infrastructure
   - Add `infra/` Bicep modules and environment parameter files.
   - Add Key Vault references and managed identities.
   - Add diagnostic settings and alerts.
   - Add deployment runbook.

7. Deployment and validation
   - Deploy dev.
   - Run migrations and seed reference data.
   - Smoke test web/API/reporting.
   - Deploy test.
   - Run full regression, PostgreSQL parity, and load tests.
   - Deploy production after go-live gates.

## Open Decisions

- Azure subscription for the isolated dev environment.
- Azure region.
- Dev environment resource naming and uniqueness suffix convention.
- Dev environment networking posture.
- Google OAuth client ownership for dev SSO.
- Azure DevOps project/repo location.
- Dev seed-data approach.
- Production domain name.
- Availability target and whether production PostgreSQL needs zone-redundant HA
  in the first release.
- Whether cloud development should use the exact production hardening switch or
  a separate cloud-hardening validation mode.
- Whether API consumers are only authenticated browser users/session-cookie
  clients for now, or whether browserless token clients must be supported in the
  first Azure release.
- Whether production starts empty with reference data or migrates existing
  operational data.
- Whether to use Azure Front Door in front of App Service. It is not required
  for the first 50-user target, but may be useful later for WAF, global routing,
  or a shared edge for web/API/MCP.

## References

- Azure App Service Django with PostgreSQL:
  https://learn.microsoft.com/en-us/azure/app-service/tutorial-python-postgresql-app-django
- Azure App Service Python configuration:
  https://learn.microsoft.com/en-us/azure/app-service/configure-language-python
- App Service Authentication:
  https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization
- Google provider for App Service Authentication:
  https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-google
- App Service authenticated user headers:
  https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-user-identities
- App Service TLS:
  https://learn.microsoft.com/en-us/azure/app-service/overview-tls
- Key Vault references in App Service:
  https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references
- Azure Database for PostgreSQL Flexible Server:
  https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview
- PostgreSQL Flexible Server compute:
  https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-compute
- PostgreSQL Flexible Server high availability:
  https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-high-availability
- PostgreSQL Flexible Server backup and restore:
  https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore
- Azure Pipelines for Python web apps:
  https://learn.microsoft.com/en-us/azure/devops/pipelines/ecosystems/python-webapp
- Azure Repos Git:
  https://learn.microsoft.com/en-us/azure/devops/repos/git/
- Azure Monitor OpenTelemetry:
  https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-configuration
- Azure Load Testing:
  https://learn.microsoft.com/en-us/azure/app-testing/load-testing/overview-what-is-azure-load-testing
