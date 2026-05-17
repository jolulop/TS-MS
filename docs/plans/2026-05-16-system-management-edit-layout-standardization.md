# System Management Edit Layout Standardization

## Goal

Apply one consistent edit-screen layout across the remaining System Management
detail pages so they match the current standalone create-page direction:

- no `Current State` panel
- the main edit form uses the full content width
- delete actions move to the bottom as a standalone action

## Scope

In scope:

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

Out of scope:

- Country and Office detail pages
- Employee detail page, already aligned separately
- approval, report, or timesheet screens

## Approach

- generalize the shared master-detail renderer so standard edit pages use the
  same top-level structure as create pages
- convert delete cards into bottom action forms
- keep custom detail screens such as Calendar on their existing template, but
  align them visually to the same pattern

## Verification

- targeted `pytest tests/test_system_management_ui.py`
- `python manage.py check`
