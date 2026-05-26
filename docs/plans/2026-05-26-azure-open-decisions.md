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
| Azure subscription | Use the user's existing Azure subscription, but deploy only to a dedicated TSMS dev resource group. | Pending confirmation | Confirm exact subscription name or ID before any Azure commands. |
| Azure region | Use a single primary region near the expected users and available PostgreSQL/App Service capacity. | Pending confirmation | For a Europe-based owner, West Europe is a reasonable starting candidate unless the business/user base says otherwise. |
| Dev resource isolation | Create `rg-tsms-dev` and environment-specific resources. | Proposed | Do not share database, Key Vault, App Service, Google OAuth client, or pipeline deploy target with other developments. |
| Resource naming | Use `app-tsms-dev`, `plan-tsms-dev`, `pg-tsms-dev`, `kv-tsms-dev`, `appi-tsms-dev`, `log-tsms-dev`, with suffixes only if Azure global uniqueness requires them. | Proposed | Key Vault and PostgreSQL names may need globally unique suffixes. |
| Dev environment hardening | Set `TSMS_ENVIRONMENT=production` in Azure dev to exercise production fail-closed checks, while using dev resources and dev data. | Proposed | Local development still uses `development` and SQLite if desired. |
| Database for dev | Use Azure Database for PostgreSQL Flexible Server. | Proposed | SQLite remains local-only. |
| Dev PostgreSQL SKU | Use a low-cost dev SKU initially. | Pending confirmation | Burstable is acceptable for dev; testing/prod should use General Purpose or better. |
| Networking for dev | Start with public access restricted to Azure services and known admin IPs, or use private access if the subscription networking is already ready. | Pending confirmation | Test/prod should move to private access/private endpoint. |
| Google SSO | Use a dev-only Google OAuth client wired to App Service Authentication. | Proposed | Do not reuse production/test OAuth client secrets. |
| API access model for Milestone 1 | Support authenticated human/session-cookie API access first. | Proposed | Browserless API clients remain an explicit later decision. |
| Production domain | Not needed for Milestone 1. | Proposed | Dev can start with `app-tsms-dev.azurewebsites.net`. |
| Production HA | Not needed for Milestone 1. | Proposed | Decide before production sizing. |
| Initial production data | Leave undecided until dev and test migration flow works. | Pending | Options: empty launch with reference data, or migrate from an existing source. |
| Future MCP | Keep as an architectural constraint only. | Confirmed for now | Do not implement MCP in Milestone 1. |

## Questions To Confirm Before Creating Azure Dev

1. Which Azure subscription should hold the TSMS dev environment?
2. Which Azure region should we use for `rg-tsms-dev`?
3. Are the names `rg-tsms-dev` and `app-tsms-dev` acceptable, with suffixes only
   where Azure requires global uniqueness?
4. Should the dev database use low-cost public access with restrictions first,
   or should we require private networking from the start?
5. Which Google account or Google Cloud project will own the dev OAuth client?
6. Should Azure DevOps/Azure Repos be created in a new project or an existing
   project?
7. Should the first Azure dev deployment seed sample dev data, or only
   reference data plus a manually created test employee?

## Recommended Milestone 1 Defaults

Unless a decision above changes, use:

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

## Exit Criteria

The open-decisions task can close when:

- Subscription is confirmed.
- Region is confirmed.
- Dev resource naming convention is confirmed.
- Dev isolation boundary is confirmed.
- Dev networking posture is confirmed.
- Google SSO ownership is confirmed.
- Azure DevOps project/repo location is confirmed.
- Dev seed-data approach is confirmed.
