# Data Model ERD v6.1

## 1. Purpose

Summarize the approved v6.1 logical data model and point to the detailed
schema diagram used in the repository.

Primary diagram:
- [database-schema-diagram.md](/home/jolulop/code/TS-MS/docs/database-schema-diagram.md)

## 2. Current Structural Highlights

- `Country` is the top-level administrative entity.
- `Office` belongs to `Country`.
- `BusinessUnit` belongs to `Office`.
- `OfficeConfiguration` is owned by `Office` and is inherited by Business Units at runtime.
- `Employee` belongs to `Office` and has a primary Business Unit plus scoped Business Unit assignments.
- `Client`, `CostCenter`, `PricingModel`, and `YearlyCalendar` are Office-level masters.
- `InternalCategory`, `GeneralChargeCode`, `Project`, and `ProjectAssignment` remain Business Unit linked.
- `CrossOfficeProjectAssignment` links an Employee to a target Project in a
  different Office while preserving origin-office context.
- `CalendarSpecialDay` belongs to `YearlyCalendar`.
- `Project` now requires `pricing_model_id`.
- v6.1 adds approved logical support for dedicated cross-office staffing on
  top of the prior admin API parity, reporting, and General Charge Code
  routing-governance baseline.

## 3. Relationship Summary

### Country owns

- Offices

### Office owns

- Business Units
- Employees
- Yearly Calendars
- Calendar Special Days
- Calendar Period Rules
  - Each rule belongs to one Business Unit plus the shared Office-level Yearly Calendar
  - Each rule can mark Saturdays and Sundays as working days and store weekend max-hours
- Clients
- Cost Centers
- Pricing Models
- Projects
- Office Configuration
- Cross-Office Staffing origin context

### Business Unit owns or scopes

- Internal Categories
- General Charge Codes
  - Each General Charge Code also references one Office-level Cost Center
- Projects
- Project Assignments
- Cross-Office Staffing origin Business Unit references
- Employee scope links

### Project classification set

Each Project references:
- one Client
- one Internal Category
- one Cost Center
- one Pricing Model
- one Project Owner employee
- one Project Manager employee

### Staffing models

- `ProjectAssignment` is the normal same-office staffing model.
- `CrossOfficeProjectAssignment` is the dedicated cross-office staffing model.
- `CrossOfficeProjectAssignment` references:
  - one Employee
  - one target Project
  - one origin Office
  - one origin Business Unit
  - one assignment status

## 4. Documentation Rule

When model behavior and older doc versions differ, treat the current diagram
and the v6.1 markdown set as the approved source-of-truth reference.
