# Working Weekends In Calendar Period Rules

## 1. Goal

Allow a Business Unit-specific Calendar Period Rule to mark Saturdays and Sundays as normal working days so those dates can be charged in the weekly timesheet unless an active Special Day overrides them back to non-working.

## 2. Scope

In scope:
- add Saturday/Sunday working flags to `CalendarPeriodRule`
- add Saturday/Sunday max-hour fields to `CalendarPeriodRule`
- expose the new flags in Calendar Period Rule create/edit UI
- make timesheet date selection and validation respect the active BU period rule
- keep active Special Days authoritative as non-working overrides
- update tests and v5.4 docs

Out of scope:
- adding BU-specific month-view behavior to the office-level Yearly Calendar detail screen

## 3. Key Rules

- by default weekends are non-working
- `working_on_saturdays_flag` makes Saturday chargeable for that BU period
- `working_on_sundays_flag` makes Sunday chargeable for that BU period
- active Special Days remain non-working even when weekend work is enabled

## 4. Assumptions

- weekly timesheet records remain Monday-starting weeks, but their stored `week_end_date` now extends to Sunday for newly created records

## 5. Outcome

- System Management can configure working Saturdays and Sundays plus their max-hours per Calendar Period Rule
- timesheet editor only offers chargeable dates for the selected week
- weekend dates can be saved when enabled and are rejected when not enabled or when overridden by a Special Day
