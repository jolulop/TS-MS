# Data Model ERD v5.8

## 1. Purpose

Summarize the current logical data model and point to the detailed schema diagram used in the repository.

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
- `CalendarSpecialDay` belongs to `YearlyCalendar`.
- `Project` now requires `pricing_model_id`.
- No structural schema changes were introduced in the v5.8 promotion itself; the release documents the Office-gated `Copy Prev. Week` behavior and its use of the existing timesheet model.

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

### Business Unit owns or scopes

- Internal Categories
- General Charge Codes
  - Each General Charge Code also references one Office-level Cost Center
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

When model behavior and older doc versions differ, treat the current diagram and the v5.8 markdown set as the repository-aligned reference.
