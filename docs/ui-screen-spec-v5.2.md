# UI Screen Specification v5.2

## Purpose

This v5.2 note captures the Milestone 2 correction pass for the server-rendered System Management UI.

Insert these updates into `docs/UI - Screen Specification  v5.1.docx` in the matching screen sections.

## Insertions for Existing Screens

### SCR-110 Employee Management

Insert after the current list-behavior section:

- Add a status filter bar with `All`, `Active`, and `Inactive`.
- Collection rows must expose an explicit `Open / Edit` action in addition to the linked primary identifier.
- The detail screen remains the update surface for employee core data, roles, and Business Unit scope.

### SCR-130 Client Management

Insert after the current list-behavior section:

- Add a status filter bar with `All`, `Active`, and `Inactive`.
- The collection screen supports create only; updates happen on the detail screen.
- The detail screen is the authoritative update surface for code, name, parent client, and lifecycle status.

### SCR-140 Internal Category Management

Insert after the current list-behavior section:

- Add a status filter bar with `All`, `Active`, and `Inactive`.
- Keep delete out of scope; lifecycle changes are handled by setting status to `INACTIVE`.

### SCR-150 Cost Center Management

Insert after the current list-behavior section:

- Add a status filter bar with `All`, `Active`, and `Inactive`.
- Keep delete out of scope; lifecycle changes are handled by setting status to `INACTIVE`.

### SCR-155 Pricing Model Management

Insert after the current list-behavior section:

- Pricing Models are managed at Office level.
- Collection supports create inside the active Office.
- Detail supports update and guarded delete.
- Fields are limited to `name` and `description`.
- Delete is blocked when a Project still references the Pricing Model.

### SCR-170 General Charge Code Management

Insert after the current list-behavior section:

- Add a status filter bar with `All`, `Active`, and `Inactive`.
- Keep delete out of scope; lifecycle changes are handled by setting status to `INACTIVE`.

## New Screens

### SCR-120 Calendar Period Rule Management

Insert as a new System Management screen after the calendar-related section:

- Purpose: manage daily hour limits through scoped calendar period rules.
- Access: `TS_ADMIN` only.
- Collection screen:
  - list columns: Business Unit, Year, Calendar, Effective From, Effective To, Status
  - filter bar: `All`, `Active`, `Inactive`
  - create form fields:
    - Yearly Calendar
    - Effective From
    - Effective To
    - Monday Max Hours
    - Tuesday Max Hours
    - Wednesday Max Hours
    - Thursday Max Hours
    - Friday Max Hours
    - Status
- Detail screen:
  - shows current state and edit form
  - supports update of dates, daily hour limits, and status
- Validation:
  - no overlapping period rules inside the same yearly calendar
  - `effective_to >= effective_from`

### SCR-180 Project Management

Insert as a new System Management screen after the classification-master section:

- Purpose: manage scoped project setup and lifecycle.
- Access: `TS_ADMIN` only in v5.2.
- Collection screen:
  - list columns: Business Unit, Project Code, Name, Status, Owner, Manager
  - filter bar: `All`, `Draft`, `Active`, `Closed`
  - create form fields:
    - Business Unit
    - Project Code
    - Project Name
    - Description
    - Project Owner
    - Project Manager
    - Client
    - Internal Category
    - Cost Center
    - Pricing Model
    - Start Date
    - End Date
    - Close Date
    - Billable
    - Status
- Detail screen:
  - shows current state and edit form
  - updates happen on the detail page
- Validation:
  - project owner must hold `PROJECT_OWNER`
  - project manager must hold `PROJECT_MANAGER`
  - client must belong to the same Office
  - cost center must belong to the same Office
  - pricing model must belong to the same Office
  - internal category must belong to the same Business Unit
  - pricing model is mandatory
  - `end_date >= start_date`
  - `close_date >= start_date`

### SCR-190 Project Assignment Management

Insert as a new System Management screen after project setup:

- Purpose: manage scoped project staffing and assignment lifecycle.
- Access: `TS_ADMIN` only in v5.2.
- Collection screen:
  - list columns: Business Unit, Project, Employee, Start, End, Status
  - filter bar: `All`, `Active`, `Inactive`
  - create form fields:
    - Project
    - Employee
    - Assignment Start Date
    - Assignment End Date
    - Status
- Detail screen:
  - shows current state and edit form
  - supports update of assignment dates and status
- Validation:
  - employee must be active
  - employee must be in the project Business Unit scope
  - closed projects cannot receive new assignments
  - assignment dates must stay inside the allowed project window

## Navigation Insertions

Insert into the System Management navigation/menu section:

- `Projects`
- `Project Assignments`
- `Calendar Period Rules`
- `Pricing Models`

## Interaction Notes

Insert into the shared list-pattern section:

- Every System Management collection with lifecycle status must expose a status filter bar.
- Every System Management collection row must expose an explicit `Open / Edit` action.
- v5.2 continues to use status changes instead of delete for these administrative records.
