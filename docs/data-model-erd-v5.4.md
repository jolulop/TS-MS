# Data Model ERD v5.4

## 1. Purpose

Summarize the current logical data model and point to the detailed schema diagram used in the repository.

Primary diagram:
- [database-schema-diagram.md](/home/jolulop/code/TS-MS/docs/database-schema-diagram.md)

## 2. Current Structural Highlights

- `Office` is the top-level administrative entity.
- `BusinessUnit` belongs to `Office`.
- `OfficeConfiguration` is owned by `Office` and is inherited by Business Units at runtime.
- `Employee` belongs to `Office` and has a primary Business Unit plus scoped Business Unit assignments.
- `Client`, `CostCenter`, and `PricingModel` are Office-level masters.
- `InternalCategory`, `GeneralChargeCode`, `Project`, `ProjectAssignment`, and `YearlyCalendar` remain Business Unit linked.
- `CalendarSpecialDay` belongs to `YearlyCalendar`.
- `Project` now requires `pricing_model_id`.

## 3. Relationship Summary

### Office owns

- Business Units
- Employees
- Yearly Calendars
- Calendar Special Days
- Calendar Period Rules
- Clients
- Cost Centers
- Pricing Models
- Projects
- Office Configuration

### Business Unit owns or scopes

- Internal Categories
- General Charge Codes
- Projects
- Project Assignments
- Employee scope links

### Project classification set

Each Project references:
- one Client
- one Internal Category
- one Cost Center
- one Pricing Model
- one Project Owner employee
- one Project Manager employee

## 4. Documentation Rule

When model behavior and older doc versions differ, treat the current diagram and the v5.4 markdown set as the repository-aligned reference.
