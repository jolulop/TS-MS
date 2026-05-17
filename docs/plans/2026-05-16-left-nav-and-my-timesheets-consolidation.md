# Left Navigation And Personal Timesheet Consolidation

## Goal

Align the authenticated shell with the new three-section left navigation and
consolidate personal timesheet browsing into a single screen:

- `My info`
- `TS/Project Management`
- `System Management`

This also removes the standalone `Session` group and merges `My Timesheets`
and `My History` into one personal list view.

## Scope

In scope:

- shared left navigation groups and labels
- `Profile` placement under `My info`
- merged personal timesheet list columns
- short-date formatting on the merged personal list
- compatibility behavior for `/ts/history/`
- targeted UI spec and test updates

Out of scope:

- timesheet editor layout changes
- report or approval feature changes beyond navigation placement
- System Management CRUD behavior

## Approach

- update the shared navigation builder once so every authenticated screen gets
  the same left-panel structure
- keep `My Timesheets` as the single personal list route and redirect
  `/ts/history/` into it
- reuse the existing timesheet summary service data and format the merged list
  at the UI layer

## Verification

- targeted `pytest tests/test_ui_shell.py tests/test_ts_management_ui.py`
- `python manage.py check`
