# Project Time Grouping Phase 1

## Goal

Add Excel-style group/ungroup behavior to `Reports > Project Time Report`
without introducing a full pivot-style engine.

Phase 1 is limited to `BU` / `Project` grouping only.

## Scope

- replace the separate Project Time weekly-summary table plus always-visible
  detail table with one grouped results grid in the HTML UI
- show one summary row per visible `BU` / `Project`
- allow each summary row to expand or collapse its child detail rows
- keep detail-row data scoped by the current server-side report filters and
  authorization rules
- keep CSV export as a flat detail export for the same filtered/scope-safe
  result set

## Non-Goals

- no nested `Week Start` grouping yet
- no pivot-table style user-defined grouping
- no client-side re-aggregation

## Approach

- shape the Project Time report payload with:
  - grouped UI rows for the browser table
  - flat detail export rows for CSV
- extend the shared report viewer so this report can render structured row
  metadata without changing the other report grids
- add lightweight expand/collapse behavior with row data attributes and a small
  inline script
- keep collapsed state as the default for Phase 1

## Validation

- update report UI tests for grouped Project Time markup
- keep Project Time CSV export coverage
- run focused `pytest` and `ruff` checks on the touched files
