# Calendar Period Rule BU Scope

## 1. Goal

Restore Business Unit ownership for `CalendarPeriodRule` so overlapping rules are only blocked inside the same Business Unit while Yearly Calendars stay Office-level.

## 2. Scope

In scope:
- add `business_unit` back to `CalendarPeriodRule`
- change overlap validation to scope by `(yearly_calendar, business_unit)`
- persist the BU selector in System Management and API flows
- resolve daily hour limits from the timesheet Business Unit
- update tests, migration, and v5.4 docs

Out of scope:
- unrelated calendar, project, or Office-management screens

## 3. Key Rules

- Yearly Calendars remain Office-level
- Calendar Period Rules are BU-specific inside the shared Office calendar
- overlapping period rules are allowed across different BUs
- overlapping period rules are rejected within the same BU and yearly calendar

## 4. Migration Strategy

- add nullable `business_unit` to `CalendarPeriodRule`
- backfill unambiguous legacy rows when an Office has exactly one Business Unit
- leave ambiguous legacy rows unassigned instead of guessing
- keep runtime fallback for legacy unassigned rules until data is cleaned up

## 5. Outcome

- Calendar Period Rule create/edit screens now persist the selected Business Unit
- API create/update requires `business_unit_id`
- daily limit resolution reads the BU-specific rule first, then legacy unassigned rules if needed
