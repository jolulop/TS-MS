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
| Dev PostgreSQL SKU | Use a low-cost dev SKU initially. | Pending confirmation | Burstable is acceptable for dev; testing/prod should use General Purpose or better. |
| Networking for dev | Start simple with restricted public PostgreSQL access. | Confirmed | Test/prod should move to private access/private endpoint. |
| Google SSO | Use a dev-only Google OAuth client owned by `jose.luis.lopez@timia.ai` and wired to App Service Authentication. | Confirmed | Do not reuse production/test OAuth client secrets. |
| API access model for Milestone 1 | Support authenticated human/session-cookie API access first. | Proposed | Browserless API clients remain an explicit later decision. |
| Azure DevOps project | Create a new Azure DevOps project for TSMS. | Confirmed | The Azure Repos Git repository will live in this new project. |
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
- Azure DevOps: create a new project

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
- App URL: `https://app-tsms-dev.azurewebsites.net`
- Auth: Google SSO through App Service Authentication
- Django environment in Azure dev: `TSMS_ENVIRONMENT=production`
- Dev auth: disabled
- Database: PostgreSQL, not SQLite
- Sample data: allowed only in dev

## Remaining Questions Before Creating Azure Dev

1. Should the first Azure dev deployment seed sample dev data, or only
   reference data plus a manually created test employee?
2. What low-cost PostgreSQL SKU should be used for dev after checking current
   regional availability and cost?
3. Which globally unique suffix should be used if `app-tsms-dev`,
   `pg-tsms-dev`, or `kv-tsms-dev` are unavailable?

## Exit Criteria

The open-decisions task can close when:

- Subscription is confirmed. Done.
- Region is confirmed. Done.
- Dev resource naming convention is confirmed. Done.
- Dev isolation boundary is confirmed. Done.
- Dev networking posture is confirmed. Done.
- Google SSO ownership is confirmed. Done.
- Azure DevOps project/repo location is confirmed. Done.
- Dev seed-data approach is confirmed.
