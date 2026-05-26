# Azure Development Environment Checklist

## Purpose

Create a new Azure development environment for TSMS that is isolated from
other Azure developments and can prove the first dev-first migration milestone.

This environment is not production, but it should still use the same deployment
shape as production where it matters:

- Azure App Service for Linux
- Azure Database for PostgreSQL Flexible Server
- Azure Key Vault
- Google SSO through Azure App Service Authentication
- HTTPS-only access
- Application Insights and Log Analytics
- Azure Repos and Azure Pipelines

## Isolation Rules

Use a dedicated resource group, dedicated names, dedicated secrets, and
environment tags. Do not share application databases, Key Vaults, app service
instances, Google OAuth clients, or pipeline deployment targets with other
developments.

Recommended resource group:

```text
rg-tsms-dev
```

Recommended resource names:

```text
app-tsms-dev
plan-tsms-dev
pg-tsms-dev
kv-tsms-dev
appi-tsms-dev
log-tsms-dev
```

Required tags:

```text
application=tsms
environment=dev
workstream=azure-migration
owner=<owner-name-or-team>
managed-by=iac
```

## Minimum Dev Resources

Create these resources for the first working development instance:

- Resource group dedicated to TSMS dev.
- App Service plan for Linux.
- App Service web app running Python 3.12.
- Azure Database for PostgreSQL Flexible Server.
- Key Vault for dev-only secrets.
- Managed identity on the App Service.
- Key Vault access for the App Service managed identity.
- Application Insights.
- Log Analytics workspace.
- Google OAuth client for the dev redirect URI.
- Azure Pipeline service connection scoped to the dev resource group where
  possible.

## Dev App Settings

The dev Azure app should behave like a hardened cloud environment, even though
it is not production. Use dev-specific hosts and secrets.

```text
TSMS_ENVIRONMENT=production
TSMS_DEBUG=0
TSMS_SECRET_KEY=@Microsoft.KeyVault(...)
TSMS_ALLOWED_HOSTS=app-tsms-dev.azurewebsites.net
TSMS_CSRF_TRUSTED_ORIGINS=https://app-tsms-dev.azurewebsites.net
TSMS_AUTH_PROVIDER=trusted-header
TSMS_ENABLE_DEV_AUTH=0
TSMS_TRUSTED_EMAIL_HEADER=HTTP_X_MS_CLIENT_PRINCIPAL_NAME

TSMS_DB_BACKEND=postgres
TSMS_DB_NAME=tsms_dev
TSMS_DB_USER=<dev-db-user>
TSMS_DB_PASSWORD=@Microsoft.KeyVault(...)
TSMS_DB_HOST=<dev-postgres-host>
TSMS_DB_PORT=5432
TSMS_DB_CONN_MAX_AGE=60
TSMS_DB_SSLMODE=require

TSMS_SESSION_COOKIE_SECURE=1
TSMS_CSRF_COOKIE_SECURE=1
TSMS_SECURE_SSL_REDIRECT=1
TSMS_ENABLE_PROXY_SSL_HEADER=1
TSMS_SECURE_PROXY_SSL_HEADER_NAME=HTTP_X_FORWARDED_PROTO
TSMS_SECURE_PROXY_SSL_HEADER_VALUE=https

TSMS_LOG_FORMAT=json
TSMS_LOG_LEVEL=INFO
TSMS_OBSERVABILITY_LOG_LEVEL=INFO
APPLICATIONINSIGHTS_CONNECTION_STRING=<dev-app-insights-connection-string>
SCM_DO_BUILD_DURING_DEPLOYMENT=true
ENABLE_ORYX_BUILD=true
TSMS_STATIC_ROOT=staticfiles
```

Using `TSMS_ENVIRONMENT=production` in Azure dev is intentional for the first
cloud milestone: it exercises the same fail-closed security checks as
production while still using isolated dev resources and dev data.

## Google SSO

Create a dev-only Google OAuth client and configure the App Service
Authentication Google provider for the dev app.

The dev redirect URI must be environment-specific. Do not reuse production or
testing Google OAuth client credentials.

Expected Django claim header:

```text
HTTP_X_MS_CLIENT_PRINCIPAL_NAME
```

Expected Django behavior:

- Azure App Service Authentication performs Google login before traffic reaches
  Django.
- On the first authenticated browser `GET /`, Django reads the trusted email
  claim, initializes the internal TS session, and redirects to `/`.
- The next `GET /` renders the normal role-aware landing page or redirects a
  basic user to `/ts/`.
- The local `validated_email` access-entry form remains a local development
  path only.

## Database

Use PostgreSQL in Azure dev. SQLite remains local-only.

Minimum readiness:

- PostgreSQL server exists.
- Dev database exists.
- App settings point to PostgreSQL.
- `python manage.py migrate` succeeds against the dev database.
- `python manage.py seed_reference_data` succeeds and is idempotent.
- Optional `python manage.py seed_dev_data` is run only in the dev environment.

## Runtime Startup

The Azure App Service startup command should run the repository startup script:

```text
bash scripts/azure-startup.sh
```

The script:

- runs `collectstatic --noinput`
- runs `manage.py check --deploy`
- starts Gunicorn against `config.wsgi:application`
- binds to Azure's `$PORT`
- reads optional Gunicorn tuning from `WEB_CONCURRENCY`,
  `GUNICORN_THREADS`, and `GUNICORN_TIMEOUT`

Required runtime dependencies:

- `gunicorn`
- `whitenoise`

Static files are served through WhiteNoise with compressed manifest storage.

## First Smoke Test

Milestone 1 is ready when all checks pass:

- App opens over HTTPS.
- Google SSO redirects and returns successfully.
- A known dev employee email maps to an active internal TS employee.
- Dashboard or TS landing page loads.
- Profile page loads and shows internal roles and BU scope.
- One timesheet page loads.
- One representative `/api/v1` endpoint returns an authorized response.
- One report page or CSV export works.
- App logs are visible in Application Insights or Log Analytics.
- The app is confirmed to be using Azure PostgreSQL, not SQLite.

## Non-Interference Checklist

Before creating or deploying dev:

- Confirm the selected subscription.
- Confirm the region.
- Confirm no existing resource group named `rg-tsms-dev` is used by another
  project.
- Confirm DNS/custom domain work is not required for Milestone 1.
- Confirm Key Vault name is globally unique or adjust it with a suffix.
- Confirm PostgreSQL server name is globally unique or adjust it with a suffix.
- Confirm the pipeline service connection cannot deploy to unrelated resource
  groups unless intentionally approved.
