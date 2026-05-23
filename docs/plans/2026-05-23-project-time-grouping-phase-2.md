# Project Time Grouping Phase 2

## Goal

Extend the grouped `Project Time Report` UI from Phase 1 so that each visible
`BU` / `Project` summary row expands to grouped `Week Start` rows, and each
week row expands to the underlying detail lines.

## Scope

- keep the grouped HTML report viewer introduced in Phase 1
- change the current project-level expand-collapse behavior to a nested model:
  - `BU` / `Project` summary row
  - `Week Start` summary row
  - detail rows
- simplify expand-collapse controls to icon-only `+` and `-`
- keep CSV export as a flat detail export with the same filters and scope rules

## Non-Goals

- no user-defined grouping dimensions
- no pivot-table behavior
- no persistence of expanded state across requests

## Approach

- reshape the Project Time report payload so grouped UI rows carry parent/child
  relationships for both project and week levels
- extend the shared report viewer to render nested grouped rows and hide all
  descendants by default
- keep the expand-collapse script lightweight and local to the report viewer
- collapse nested week/detail rows again when a project row is collapsed

## Validation

- update Project Time UI tests for project and week grouping markup
- keep Project Time CSV export tests flat
- run focused `pytest` and `ruff` checks on the touched files
