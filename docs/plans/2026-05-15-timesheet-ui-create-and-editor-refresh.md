# Timesheet UI Create And Editor Refresh

## Goal

Refresh the employee timesheet UI so the list page focuses on existing
timesheets, creation starts from header controls in one click, and the
edit/detail screen becomes wider and cleaner.

## Source Documents

- `AGENTS.md`
- `docs/functional-spec-v5.4.md`
- `docs/ui-screen-spec-v5.4.md`

## Scope

In scope:

- remove the inline create panel from `My Timesheets`
- add header-level `Week Start Date` selection and `Create Timesheet` action
- keep the create flow on the list screen with the selected date only
- widen the weekly list presentation and remove the redundant list section label
- remove the `Timesheet Context` and `Available Charge Targets` panels from the
  timesheet detail UI
- keep only the requested metadata fields under the week title
- widen the timesheet editor area
- preload new timesheets with five empty editor rows
- add editable row controls to remove rows and append rows
- add a draft-only delete action for employee-owned timesheets
- update UI tests and screen documentation

Out of scope:

- changing timesheet business rules, authorization, or approval logic
- adding new JSON endpoints

## Approach

- keep `/ts/` as the collection page and visible create entrypoint
- use progressive enhancement on the editor page for row add/remove controls,
  while keeping server-side validation authoritative
- allow deletion only for employee-owned `CREATED` timesheets without submission
  history, and audit successful deletes

## Verification

- targeted `pytest tests/test_ts_management_ui.py`
- `python manage.py check`
