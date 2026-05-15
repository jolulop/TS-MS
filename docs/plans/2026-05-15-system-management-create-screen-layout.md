# System Management Create Screen Layout

## Goal

Apply the new Employee-style System Management layout to the remaining admin
screens that still combine records and create forms on the same collection page.

## Scope

In scope:

- move collection status filters into the records card header
- remove the standalone filter panel for the affected collection screens
- remove inline create forms from those collection screens
- add header-level `Create ...` buttons
- add standalone `/new/` create pages for the affected entities
- remove the `Current State` panel from those standalone create pages
- widen records-first collection layouts
- update UI tests for new navigation and create flows

Out of scope:

- Office and Country screens
- Timesheet, Approval, and Report screens
- changing underlying create/update business rules

## Affected Screens

- Business Units
- Clients
- Projects
- Project Assignments
- Internal Categories
- Cost Centers
- Pricing Models
- Calendars
- Calendar Period Rules
- General Charge Code Approval Roles
- General Charge Codes

## Approach

- generalize the shared collection/detail rendering helpers instead of patching
  each template ad hoc
- keep collection create POST compatibility where useful for tests and backward
  resilience, but route the visible UI through dedicated create screens
- use one consistent create-page pattern:
  - header title `Create <Entity>`
  - setup section title `<Entity> Setup`
  - no `Current State` panel
  - back action to the collection screen

## Verification

- targeted `pytest` for `tests/test_system_management_ui.py`
- targeted `pytest` for `tests/test_ui_shell.py`
- `manage.py check`
