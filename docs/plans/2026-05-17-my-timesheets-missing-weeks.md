# My Timesheets Missing Weeks

## Goal

Show missing weekly timesheets directly in the personal `My Timesheets` list so
employees can spot gaps and jump into the create flow for the missing week.

## Scope

In scope:

- detect missing Monday-starting weeks since employee record creation
- insert synthetic `Missing` rows into the merged personal timesheet list
- link missing rows back to the timesheet create controls with the week
  preselected
- update focused docs and UI tests

Out of scope:

- changing create validation rules
- changing reporting-side missing-timesheet logic
- backfilling or auto-creating timesheets without user action

## Approach

- extend the personal timesheet summary service to merge real timesheets with
  computed missing-week rows
- use the employee record `created_at` date as the starting point for gap
  detection
- start gap detection from the first Monday on or after the employee creation
  date and continue through the current Monday only
- keep the page route the same and use a query parameter to preload the create
  week in the existing header controls

## Verification

- targeted `pytest tests/test_ts_management_ui.py`
- `python manage.py check`
