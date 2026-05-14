# Country Entity For Offices

## Goal

Add a real `Country` master entity above `Office`, make every Office belong to
one Country, and let `TS_ADMIN_MASTER` users manage Countries from System
Management.

## Scope

In scope:

- schema change for new `Country` table
- mandatory `Office.country` foreign key
- backfill strategy for existing Office rows
- System Management Country CRUD UI for `TS_ADMIN_MASTER`
- Office create/edit UI updates to require a Country selection
- service, helper, seed, and documentation updates
- regression coverage

Out of scope:

- changing employee authorization to become Country-scoped
- adding Country to downstream employee/project/client APIs unless already
  implied by Office

## Design

### Data model

- add `Country` with:
  - `country_code`
  - `country_name`
  - `status`
- add mandatory `country` FK on `Office`
- keep current Office-centric downstream relations unchanged

### Backfill

- create one Country row for each existing Office during migration
- derive a stable `country_code` from `office_name`
- assign each existing Office to its generated Country
- leave later cleanup/normalization to admin users if needed

### UI

- add a new `Countries` section for `TS_ADMIN_MASTER`
- support create, edit, delete, and status filtering
- add Country dropdown to Office create/edit forms
- show Country in Office collection/detail views

### Seed data

- add sample Countries:
  - `Holding`
  - `España`
  - `Peru`
- assign sample Offices:
  - `Holding` -> `Holding`
  - `Lima` -> `Peru`
  - `Madrid` -> `España`

## Risks

- many tests currently create Offices directly, so helpers must absorb the new
  required foreign key cleanly
- current code still uses historic `COUNTRY_STATUS` naming for Office status; we
  will avoid broad renaming in this change to keep scope contained

## Verification

- targeted UI tests for Country CRUD and Office Country selection
- targeted service/API tests where applicable
- `manage.py check`
- `makemigrations --check --dry-run`
