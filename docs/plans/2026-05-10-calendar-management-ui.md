# Calendar Management UI

## 1. Goal

Add Yearly Calendar and Calendar Special Day management to System Management, including a calendar-oriented UI, CRUD flows, and the new special-day type values requested by the business.

## 2. Scope

In scope:
- Yearly Calendar create, edit, delete
- Calendar Special Day create, edit, delete
- a new System Management `Calendars` section
- month-view and summary display for a selected calendar
- new `SPECIAL_DAY_TYPE` reference values
- BU scope enforcement in services and UI

Out of scope:
- changing period-rule behavior
- changing timesheet hour calculations beyond existing special-day semantics
- Office-level calendar management

## 3. Affected Modules

- `apps/reference_data/seeds.py`
- `apps/master_data/services.py`
- `apps/master_data/views.py`
- `apps/master_data/urls.py`
- `apps/core/system_views.py`
- `apps/core/views.py`
- `apps/core/urls.py`
- `templates/base.html`
- new calendar-specific templates
- tests and helper utilities

## 4. Design Notes

- Keep Yearly Calendars Business Unit scoped.
- Keep the existing Calendar Period Rule UI and add a separate `Calendars` section.
- Treat special-day deletion as a simple guarded delete with no cascade cleanup.
- Generate special-day `name` automatically from day type and date because the UI request only exposes date and type.

## 5. Risks

- old `SPECIAL_DAY_TYPE` values (`HOLIDAY`, `COMPANY_DAY`) need safe migration to the new requested set
- custom month-view UI needs to stay readable on mobile

## 6. Outcome

- added a new `Calendars` System Management section
- added Yearly Calendar create, edit, guarded delete, month view, and summary UI
- added Calendar Special Day create, edit, and guarded delete UI
- added Yearly Calendar and Calendar Special Day JSON admin endpoints
- refreshed `SPECIAL_DAY_TYPE` values to:
  - `NATIONAL_HOLIDAY`
  - `LOCAL_HOLIDAY`
  - `TIMIA_DAY`
  - `OTHER`
