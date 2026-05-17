# 2026-05-17 My Timesheets Filters And Personal Report Removal

## Goal

Improve `My info > My Timesheets` by adding the same personal history filters
that were previously exposed under `Reports > My Timesheet History`, and remove
the duplicate personal-history entry from the Reports area.

## Scope

- add `Status`, `Week Start From`, and `Week Start To` filters to `/ts/`
- keep the existing create-timesheet controls in the page header
- filter both real timesheets and synthetic `Missing` rows in the merged list
- remove `My Timesheet History` from the Reports hub
- redirect the legacy `/reports/my-timesheet-history/` route to `/ts/`
  preserving query-string filters for compatibility

## Notes

- `My Timesheets` is now the single personal weekly timeline for all roles.
- The compatibility redirect is preferred over a hard 404/403 because users may
  still have bookmarks or older links.
