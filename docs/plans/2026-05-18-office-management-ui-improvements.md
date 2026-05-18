# Office Management UI Improvements

## 1. Goal

Refine the `TS_ADMIN_MASTER` Office Management experience so the collection and detail screens surface the requested information and follow the newer standalone create/edit layout.

## 2. Scope

In scope:
- Office Management collection layout changes
- Office employee-count column
- standalone Office create screen
- Office detail layout simplification
- affected tests and current v5.6 markdown docs

Out of scope:
- Office business-rule changes
- non-Office System Management screens except shared template support required by the Office UI

## 3. Source Documents

- `docs/functional-spec-v5.6.md`
- `docs/ui-screen-spec-v5.6.md`
- `docs/use-cases-acceptance-v5.6.md`
- `AGENTS.md`

## 4. Affected Areas

- `apps/core/system_views.py`
- `apps/core/urls.py`
- `apps/master_data/services.py`
- `templates/core/system_collection.html`
- `templates/base.html`
- `tests/test_system_management_ui.py`
- current v5.6 docs

## 5. UI Changes

- move Office status filter links into the page-title row on the collection screen
- remove the `Current Records` heading from the Office grid
- add an `Employees` column showing the number of active employees in each Office
- remove inline Office creation from the collection screen
- add a bottom `Create Office` button that opens a standalone Office creation screen
- remove the `Current State` panel from Office detail
- widen Office edit/create form sections to a single full-width column

## 6. Service Changes

- annotate Office collection rows with active employee count
- keep Office create and edit business behavior unchanged

## 7. Tests

- Office collection shows the employee-count column and standalone-create button
- Office collection no longer renders the inline create form
- Office create works through `/system/offices/new/`
- Office detail no longer renders the `Current State` panel

## 8. Verification Notes

- Focused Office/System Management UI tests should pass
- shared-template changes should be checked against the wider suite because they affect other collection screens
