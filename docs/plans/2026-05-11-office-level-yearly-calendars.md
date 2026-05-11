# Office-Level Yearly Calendars

## 1. Goal

Move `YearlyCalendar` from Business Unit ownership to Office ownership so all Business Units in an Office share the same yearly calendar for a given year.

## 2. Scope

In scope:
- change `YearlyCalendar` schema and constraints
- adapt Yearly Calendar and dependent calendar-management services
- adapt Calendar Management UI to remove Business Unit selection
- update related period-rule and special-day calendar lookups that still assume BU ownership
- update tests, seed data, and v5.4 docs

Out of scope:
- unrelated System Management screens

## 3. Key Rules

- Yearly Calendar belongs to Office, not Business Unit
- only one Yearly Calendar can exist for a given year in an Office
- Yearly Calendar creation is always bound to the active Office
- Business Units inherit the Office calendar behavior at runtime

## 4. Risks

- existing databases may already contain multiple calendars for the same Office/year
- period-rule and special-day flows currently serialize and scope calendars through Business Unit data

## 5. Migration Strategy

- remove the direct `business_unit` foreign key from `YearlyCalendar`
- enforce uniqueness on `(office, calendar_year)`
- consolidate existing calendars per `(office, calendar_year)` during migration when child data can be merged safely
- fail fast if conflicting calendar child data would make consolidation ambiguous

## 6. Outcome

- `YearlyCalendar` now belongs to `Office`, not `BusinessUnit`
- Calendar create/update flows no longer accept a Business Unit
- only one Yearly Calendar can exist for a given Office/year
- existing duplicate Office/year calendars are consolidated during migration when their child data can be merged safely
- calendar detail, special-day flows, and period-rule screens now read calendar Office context instead of Business Unit context
