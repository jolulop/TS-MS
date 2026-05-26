# Azure Migration Open Decisions

Status: in progress
Date: 2026-05-26
Related epic: TSMS Azure Migration
Related milestone: Milestone 1 - Working Azure Development Instance

## Purpose

Capture the decisions that must be confirmed before creating the first isolated
Azure development environment and before promoting the architecture to testing
and production.

The immediate target is a working development instance that does not interfere
with other Azure work.

## Decision Log

| Decision | Recommendation | Status | Notes |
| --- | --- | --- | --- |
| Azure subscription | Use subscription `43bef7fd-2d3e-4f34-8c31-5c40cfc24ca0`. | Confirmed | Deploy only to a dedicated TSMS dev resource group. |
| Azure region | Use Azure region `West Europe` (`westeurope`). | Confirmed | User requested Western Europe; Azure canonical location is `westeurope`. |
| Dev resource isolation | Create `rg-tsms-dev` and environment-specific resources. | Confirmed | Do not share database, Key Vault, App Service, Google OAuth client, or pipeline deploy target with other developments. |
| Resource naming | Use `app-tsms-dev`, `plan-tsms-dev`, `pg-tsms-dev`, `kv-tsms-dev`, `appi-tsms-dev`, `log-tsms-dev`, with suffixes only if Azure global uniqueness requires them. | Confirmed | App Service, Key Vault, and PostgreSQL names may need globally unique suffixes. |
| Dev environment hardening | Set `TSMS_ENVIRONMENT=production` in Azure dev to exercise production fail-closed checks, while using dev resources and dev data. | Proposed | Local development still uses `development` and SQLite if desired. |
| Database for dev | Use Azure Database for PostgreSQL Flexible Server. | Proposed | SQLite remains local-only. |
| Dev PostgreSQL SKU | Use `Standard_B1ms` for the first dev instance. | Confirmed | SKU is available in `westeurope`; testing/prod should use General Purpose or better. |
| Networking for dev | Start simple with restricted public PostgreSQL access. | Confirmed | Test/prod should move to private access/private endpoint. |
| Google SSO | Use a dev-only Google OAuth client owned by `jose.luis.lopez@timia.ai` and wired to App Service Authentication. | Confirmed | Do not reuse production/test OAuth client secrets. |
| API access model for Milestone 1 | Support authenticated human/session-cookie API access first. | Proposed | Browserless API clients remain an explicit later decision. |
| Azure DevOps project | Create a new Azure DevOps project for TSMS in `https://dev.azure.com/timia-innovacion`. | Confirmed | The Azure Repos Git repository will live in this new project. |
| Dev seed data | Run reference seed data and dev sample data in Azure dev. | Confirmed | Dev sample data must not be used in test or production. |
| Production domain | Not needed for Milestone 1. | Proposed | Dev can start with `app-tsms-dev.azurewebsites.net`. |
| Production HA | Not needed for Milestone 1. | Proposed | Decide before production sizing. |
| Initial production data | Leave undecided until dev and test migration flow works. | Pending | Options: empty launch with reference data, or migrate from an existing source. |
| Future MCP | Keep as an architectural constraint only. | Confirmed for now | Do not implement MCP in Milestone 1. |

## Confirmed Milestone 1 Inputs

- Subscription ID: `43bef7fd-2d3e-4f34-8c31-5c40cfc24ca0`
- Azure region: `West Europe`
- Azure CLI location: `westeurope`
- Resource group: `rg-tsms-dev`
- App name base: `app-tsms-dev`
- Dev networking: restricted public PostgreSQL access for Milestone 1
- Google SSO owner: `jose.luis.lopez@timia.ai`
- Azure DevOps organization: `https://dev.azure.com/timia-innovacion`
- Azure DevOps: create a new project
- Dev PostgreSQL SKU: `Standard_B1ms`
- Dev seed data: reference data plus dev sample data

## Azure Read-Only Checks

Performed on 2026-05-26 with Azure CLI after device-code login:

- Active subscription: `Suscripción de Azure 1`
  (`43bef7fd-2d3e-4f34-8c31-5c40cfc24ca0`)
- Tenant: `f7ffa10c-7401-4641-bcd7-f80610180c42`
- Resource group `rg-tsms-dev`: did not exist before creation
- App Service name `app-tsms-dev`: available
- Key Vault name `kv-tsms-dev`: available
- PostgreSQL Flexible Server name `pg-tsms-dev`: available
- PostgreSQL Flexible Server SKU `Standard_B1ms`: available in `westeurope`
- Azure DevOps organization: `https://dev.azure.com/timia-innovacion`

## Azure Resource Creation Log

- 2026-05-26: Created resource group `rg-tsms-dev` in `westeurope` under
  subscription `43bef7fd-2d3e-4f34-8c31-5c40cfc24ca0`.
  - Tags: `application=tsms`, `environment=dev`,
    `workstream=azure-migration`, `owner=jose.luis.lopez@timia.ai`,
    `managed-by=manual-bootstrap`
- 2026-05-26: Created Azure DevOps project `TSMS` in organization
  `https://dev.azure.com/timia-innovacion`.
  - Project ID: `05e24c41-9f94-4839-8708-f2075a261802`
  - Visibility: private
  - Process: Agile
  - Source control: Git
  - Default team: `TSMS Team`
  - Default repo: `TSMS`
  - Repo ID: `0174ef9e-fb75-48e6-865b-65e757cf644b`
  - Repo URL: `https://dev.azure.com/timia-innovacion/TSMS/_git/TSMS`
- 2026-05-26: Created dev observability and runtime foundation resources in
  `rg-tsms-dev`.
  - Log Analytics workspace: `log-tsms-dev`
  - Application Insights: `appi-tsms-dev`
  - Key Vault: `kv-tsms-dev`
  - App Service plan: `plan-tsms-dev`, Linux Basic B1
  - Web app: `app-tsms-dev`
  - Web app URL: `https://app-tsms-dev.azurewebsites.net`
  - Web app runtime: Python 3.12
  - Web app settings: HTTPS-only, TLS 1.2 minimum, FTPS disabled, client
    affinity disabled
  - Web app managed identity principal ID:
    `a27e9dac-1f42-4845-8971-407d77bd2f9c`
- 2026-05-26: Granted Key Vault RBAC for dev secret handling.
  - `app-tsms-dev` managed identity: `Key Vault Secrets User`
  - Signed-in user object ID `785c8835-5a64-4ac7-ac0f-62ade3ccca82`:
    `Key Vault Secrets Officer`
- 2026-05-26: Created and configured PostgreSQL dev database resources.
  - Flexible Server: `pg-tsms-dev`
  - SKU: `Standard_B1ms`
  - PostgreSQL version: 16
  - Host: `pg-tsms-dev.postgres.database.azure.com`
  - Database: `tsms_dev`
  - Public access: Azure services/resources allowed for Milestone 1
  - Admin user: `tsmsadmin`
  - Password storage: `tsms-db-password` in `kv-tsms-dev`
  - The initial generated PostgreSQL password was rotated immediately because
    Azure CLI printed it in the server-create JSON output.
- 2026-05-26: Stored dev application secrets in Key Vault.
  - `tsms-secret-key`
  - `tsms-db-password`
  - App Service Key Vault references for `TSMS_SECRET_KEY` and
    `TSMS_DB_PASSWORD` are resolved.
- 2026-05-26: Configured `app-tsms-dev` application settings for hardened Azure
  dev.
  - `TSMS_ENVIRONMENT=production`
  - `TSMS_DEBUG=0`
  - `TSMS_AUTH_PROVIDER=trusted-header`
  - `TSMS_ENABLE_DEV_AUTH=0`
  - PostgreSQL environment values for `tsms_dev`
  - secure cookie and proxy HTTPS settings
  - JSON logging and Application Insights connection string

## Current Blockers

- Azure Repos Git push from this machine is pending credentials.
  - Azure DevOps project and repo exist.
  - Local Git remote `azure` was added to this worktree.
  - Azure CLI can manage DevOps resources, but Git push rejected the Azure CLI
    access token.
  - Git Credential Manager is not installed in this environment.
  - Next options: create a short-lived Azure DevOps PAT for initial push, or
    install/configure Git Credential Manager locally.
- Google SSO is pending the dev Google OAuth client ID and secret.
  - Owner: `jose.luis.lopez@timia.ai`
  - Target app URL: `https://app-tsms-dev.azurewebsites.net`
- Application code is not deployed yet.
  - Runtime resources and app settings exist.
  - Code still needs Azure runtime changes, packaging, deployment pipeline, and
    migration/seed execution.

## Recommended Milestone 1 Defaults

Unless a decision above changes, use:

- Subscription: `43bef7fd-2d3e-4f34-8c31-5c40cfc24ca0`
- Region: `westeurope`
- Resource group: `rg-tsms-dev`
- App Service: `app-tsms-dev`
- App Service plan: `plan-tsms-dev`
- PostgreSQL server: `pg-tsms-dev` plus unique suffix if needed
- Database: `tsms_dev`
- Key Vault: `kv-tsms-dev` plus unique suffix if needed
- Application Insights: `appi-tsms-dev`
- Log Analytics: `log-tsms-dev`
- PostgreSQL SKU: `Standard_B1ms`
- App URL: `https://app-tsms-dev.azurewebsites.net`
- Auth: Google SSO through App Service Authentication
- Django environment in Azure dev: `TSMS_ENVIRONMENT=production`
- Dev auth: disabled
- Database: PostgreSQL, not SQLite
- Seed data: reference data plus dev sample data

## Remaining Questions Before Creating Azure Dev

No blocking open questions remain for creating the isolated development
resource group.

If a later resource creation command reports a name collision despite the
availability checks, append a short unique suffix to that specific globally
scoped resource name and update this decision log.

## Exit Criteria

The open-decisions task can close when:

- Subscription is confirmed. Done.
- Region is confirmed. Done.
- Dev resource naming convention is confirmed. Done.
- Dev isolation boundary is confirmed. Done.
- Dev networking posture is confirmed. Done.
- Google SSO ownership is confirmed. Done.
- Azure DevOps project/repo location is confirmed. Done.
- Dev seed-data approach is confirmed. Done.
