# Azure Production Deployment Checklist

## Purpose

Production deployments must fail closed when security-critical settings are
missing. Local SQLite and development email login remain available only for
development bootstrap.

## Required Environment

- `TSMS_ENVIRONMENT=production`
- `TSMS_DEBUG=0`
- `TSMS_SECRET_KEY=<Key Vault backed secret>`
- `TSMS_ALLOWED_HOSTS=<app-host>,<custom-domain>`
- `TSMS_CSRF_TRUSTED_ORIGINS=https://<app-host>,https://<custom-domain>`
- `TSMS_AUTH_PROVIDER=trusted-header`
- `TSMS_ENABLE_DEV_AUTH=0`
- `TSMS_TRUSTED_EMAIL_HEADER=HTTP_X_MS_CLIENT_PRINCIPAL_NAME`

## Database

Use PostgreSQL for production parity:

- `TSMS_DB_BACKEND=postgres`
- `TSMS_DB_NAME=<database>`
- `TSMS_DB_USER=<user>`
- `TSMS_DB_PASSWORD=<Key Vault backed secret>`
- `TSMS_DB_HOST=<postgres-host>`
- `TSMS_DB_PORT=5432`
- `TSMS_DB_CONN_MAX_AGE=60`
- `TSMS_DB_SSLMODE=require`

`TSMS_DB_SSLMODE=require` is the Azure PostgreSQL default expectation. Raise it
to `verify-full` only after certificate authority and hostname validation are
configured deliberately.

## HTTPS And Cookies

Production defaults expect HTTPS termination at Azure ingress:

- `TSMS_SESSION_COOKIE_SECURE=1`
- `TSMS_CSRF_COOKIE_SECURE=1`
- `TSMS_SECURE_SSL_REDIRECT=1`
- `TSMS_ENABLE_PROXY_SSL_HEADER=1`
- `TSMS_SECURE_PROXY_SSL_HEADER_NAME=HTTP_X_FORWARDED_PROTO`
- `TSMS_SECURE_PROXY_SSL_HEADER_VALUE=https`

Optional HSTS hardening after the HTTPS path is verified:

- `TSMS_SECURE_HSTS_SECONDS=31536000`
- `TSMS_SECURE_HSTS_INCLUDE_SUBDOMAINS=1`
- `TSMS_SECURE_HSTS_PRELOAD=1`

## Identity

Google SSO or Azure-authenticated ingress must authenticate the user before
traffic reaches Django and forward only a trusted email claim to TS. TS then
resolves the employee, roles, Office, and Business Unit scope from internal
application data.

## Secret Storage

Store production secrets in Azure Key Vault or an equivalent managed secret
store. Do not use `.env.example` values in production.

## Observability

Production defaults emit JSON application logs suitable for Azure log ingestion:

- `TSMS_LOG_FORMAT=json`
- `TSMS_LOG_LEVEL=INFO`
- `TSMS_OBSERVABILITY_LOG_LEVEL=INFO`

Route stdout/stderr to Azure Application Insights, Azure Monitor, or the
equivalent platform log pipeline. Structured observability events currently
cover access denials, approval workflow conflicts, and report CSV exports.

## Runtime

Production App Service deployments should use:

- startup command: `bash scripts/azure-startup.sh`
- WSGI server: Gunicorn
- static files: WhiteNoise compressed manifest storage

Tune these only after load testing:

- `WEB_CONCURRENCY`
- `GUNICORN_THREADS`
- `GUNICORN_TIMEOUT`
