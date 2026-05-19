# System Management UI Consistency Cleanup

## Goal

Standardize the System Management experience so collection screens, standalone create
screens, detail layouts, filters, and guarded delete actions follow the same visual
and interaction pattern.

## Scope

- finish the standalone create-screen pattern for remaining CRUD outliers
- normalize shared collection template copy and filter presentation
- normalize bottom delete action presentation on detail screens
- keep business rules, permissions, and delete guard behavior unchanged

## Changes

- move Country creation from the collection screen to a standalone create screen
- keep collection status filters inline and remove legacy filter-helper copy
- render action-only bottom delete actions as titled danger sections
- align Employee delete with the shared guarded-delete section pattern

## Verification

- focused System Management UI tests
- focused shell navigation tests
- Django system check
- Ruff on touched files

## Status

- completed
