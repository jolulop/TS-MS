# Cross-Office Staffing Option 4 Implementation Blueprint

## 1. Goal

Introduce a dedicated cross-office staffing model that allows an employee from
Office A to charge time to a project owned by Office B without changing the
employee's home Office, calendar, calendar period rules, or General Charge
Code context.

This blueprint implements the explicit-model variant of the earlier Option 4
design. It does **not** use a special employee role as the core mechanism.

## 2. Locked Business Rules

The following rules are treated as approved inputs for this blueprint:

- the employee always uses the employee's home-office calendar
- the employee always uses the employee's home-office calendar period rules
- the employee always uses the employee's home-office General Charge Codes
- if the employee's home office marks a day as holiday, the employee must
  charge holiday time and must not charge the other office's project
- if the target office marks a day as holiday but the employee's home office
  treats it as a working day, the employee may charge project time or an
  origin-office GCC such as `OC_Holiday`, depending on business handling
- project-office approvers must approve project time regardless of employee
  origin office
- project-time reporting must include all assigned employees regardless of
  employee origin office

## 3. Recommended Scope Boundary

To keep the first delivery coherent and reviewable, the implementation should
support these outcomes in Phase 1:

- cross-office staffing records can be created, edited, listed, and deleted
- timesheet project eligibility accepts either a normal assignment or a
  cross-office staffing record
- project approval routing works for cross-office project time
- project staffing summaries and missing-timesheet views recognize both models
- project-time reporting includes cross-office charged time

The implementation should **not** automatically expand all Office/BU summary
reports to project-office attribution in Phase 1. Those reports currently use
the timesheet home-BU side and should remain so unless a separate reporting
change is approved.

## 4. Target Domain Design

### 4.1 New Entity

Add a new model named `CrossOfficeProjectAssignment`.

Purpose:

- represent staffing where the employee office differs from the target project
  office
- keep same-office staffing on the existing `ProjectAssignment` model
- preserve an explicit audit trail for exceptional staffing

Recommended fields:

- `project`
- `employee`
- `origin_office`
- `origin_business_unit`
- `assignment_start_date`
- `assignment_end_date`
- `status`
- `justification_text`
- standard audit fields inherited from `AuditFieldsModel`

Recommended semantics:

- `project.office != origin_office` is mandatory
- `employee.office == origin_office` is mandatory at creation time
- `origin_business_unit` is stored as a snapshot/reference for audit and UI
  visibility, not as the source of approval or project authorization
- `employee`, `project`, `origin_office`, and `origin_business_unit` become
  immutable after creation

### 4.2 Why Store Origin Office And Origin BU Explicitly

The current employee-transfer workflow can archive and recreate employees
across offices. If origin office is derived only from the current employee
record, historical staffing context becomes ambiguous after later transfers.

Persisting `origin_office` and `origin_business_unit` gives us:

- stable audit meaning
- clearer UI labels
- consistent reporting labels for project staffing history
- simpler transfer blocker logic

## 5. Schema And Migration Blueprint

### 5.1 New Table

Add a new table in `apps/master_data/models.py` and a forward-only migration.

Recommended constraints:

- unique `(project, employee, assignment_start_date)`
- check `assignment_end_date >= assignment_start_date` when end date exists
- application-level validation that project office differs from origin office
- application-level validation that the employee office matches origin office
- application-level validation that the employee is active
- application-level validation that the project is active and not closed for
  new assignments

### 5.2 Overlap Validation

Database constraints cannot safely prevent overlapping windows across two
different tables. Add service-level validation to block:

- overlap with another `CrossOfficeProjectAssignment`
- overlap with a normal `ProjectAssignment` for the same employee/project/date
  window when the business wants only one staffing source per window

Recommended rule:

- do not allow overlapping active windows across the two models for the same
  employee/project combination

### 5.3 Transfer Blockers

Update employee-transfer blocker detection so active cross-office staffing is
treated like active project assignments. A cross-office staffed employee must
not transfer until those target-office dependencies are resolved.

## 6. UI Blueprint

### 6.1 New Management Surface

Add a new System Management surface:

- `Cross-Office Staffing`

Recommended placement:

- under `Project Assignments`

Recommended visibility:

- `TS_ADMIN`
- `PROJECT_OWNER`
- `PROJECT_MANAGER`

Scope remains based on the **target project** they are allowed to manage, not
on the employee's origin office.

### 6.2 Collection Screen

Add a collection page similar to `Project Assignment Management`, but with
cross-office-specific filters and columns.

Recommended filters:

- Status
- Target Office
- Client
- Project
- Origin Office
- Employee

Recommended columns:

- Target Office
- Target BU
- Client
- Project Code
- Project Name
- Origin Office
- Origin BU
- Employee Code
- Employee Name
- Start Date
- End Date
- Status

### 6.3 Create/Edit Form

Avoid a single unfiltered employee dropdown across all offices. Use a guided
selection flow:

1. pick target project
2. show target office and target BU as read-only derived fields
3. pick origin office
4. filter eligible active employees within that origin office
5. enter assignment dates and justification

Recommended form fields:

- Project
- Origin Office
- Employee
- Origin BU read-only summary
- Assignment Start Date
- Assignment End Date
- Status
- Justification

### 6.4 Existing UI Changes

Update these existing screens to union normal assignments and cross-office
staffing where the screen is conceptually about project staffing:

- `TS/Project Management > Project Management` employee counts
- `Missing Timesheets by Project`
- project staffing drill-downs
- employee detail staffing sections

Do **not** merge the two models into the same maintenance form in Phase 1.
Keep the normal and cross-office flows explicit.

## 7. Service And Policy Blueprint

### 7.1 New Management Service

Add a dedicated service, recommended name:

- `CrossOfficeProjectAssignmentManagementService`

Responsibilities:

- create/list/get/update/delete cross-office staffing
- validate office mismatch rules
- validate date windows
- validate overlap against both staffing models
- enforce target-project management scope
- write audit events

### 7.2 Shared Staffing Resolver

Introduce a shared staffing helper used by multiple modules. Recommended
names:

- `StaffingEligibilityService`
- or a lower-level helper module in `apps/timesheets/services.py`

Core queries to centralize:

- employee has active normal assignment for project/date
- employee has active cross-office staffing for project/date
- employee has active staffing of either type for project/date
- available projects for a week from both models
- staffing windows for project staffing and missing-timesheet reports from both
  models

This shared resolver is the key design move that keeps Option 4 maintainable.
Without it, the codebase will duplicate union logic in views and reports.

### 7.3 Authorization Rules

Recommended Phase 1 rule:

- management authority follows the target project, not the employee origin
  office

Meaning:

- target-office `TS_ADMIN` may manage cross-office staffing for scoped target
  projects
- target project owner may manage cross-office staffing for owned projects
- target project manager may manage cross-office staffing for managed projects

This keeps staffing, project charging, and project approvals aligned around the
target project.

## 8. Timesheet Engine Blueprint

### 8.1 Existing Hotspots

Current project eligibility is hard-coded to the normal `ProjectAssignment`
model in:

- `apps/timesheets/services.py::_get_project_for_line`
- `apps/timesheets/services.py::_available_projects_for_week`

### 8.2 Required Change

Replace the direct `ProjectAssignment` checks with a shared eligibility call:

- `employee_has_project_staffing(employee, project, work_date)`
- `available_projects_for_week(timesheet)`

The helper must return true when either of these is active for the work date:

- normal assignment
- cross-office staffing assignment

### 8.3 What Must Not Change

Do **not** change these home-office semantics:

- weekly timesheet remains on the employee home BU
- GCC validation remains against the timesheet BU
- calendar special days remain based on the employee's assigned calendar
- period-rule lookup remains based on the employee's assigned calendar and the
  timesheet BU

This directly matches the business rules you gave.

## 9. Approval Blueprint

### 9.1 Project Approval

Project approvals should continue to route by project ownership/management.
Cross-office staffing should only make the employee eligible to charge the
project. It should not create a separate approval path.

Expected result:

- project office approval sees and can action project time from origin-office
  employees

### 9.2 TS_ADMIN Oversight

Current `TS_ADMIN` oversight is still based on the weekly-timesheet home BU.
That is a separate concern from project approval routing.

Recommended blueprint split:

- Phase 1: leave `TS_ADMIN` oversight unchanged
- Phase 2 optional: add target-project-office oversight for selected approval
  worklist and report views

This keeps the first delivery aligned to your stated requirement without
forcing a broader admin-oversight redesign.

## 10. Reporting Blueprint

### 10.1 Must Change In Phase 1

Update staffing-derived and project-derived reports/views so they understand
both staffing models:

- `Project Time Report`
  - no change to line source
  - ensure project-scoped visibility continues to include cross-office charged
    lines
- `Missing Timesheets by Project`
  - union normal assignment windows and cross-office staffing windows
- `TS/Project Management > Project Management`
  - employee counts and pending staffing-based summaries must see both models

### 10.2 Should Stay Home-BU Based In Phase 1

Unless new requirements are approved, these should remain based on the
timesheet/home BU model:

- `Office / BU Time Summary`
- `Employee Utilization`
- `General Charge Code Usage`
- `Archived Timesheets`
- `Audit History`
- `Integration Jobs`

### 10.3 Recommended Clarification For Project Time Report

The current report shows the timesheet BU. With cross-office staffing, that BU
may be the employee home BU rather than the target project BU.

Recommended Phase 1 enhancement:

- keep existing BU column as the employee home/timesheet BU
- add optional columns or labels for:
  - Project Office
  - Project BU
  - Origin Office

If UI expansion is undesirable, at minimum update the spec wording so the BU
label is not misread as project ownership attribution.

## 11. File-Level Impact Map

Expected code changes will center on:

- `apps/master_data/models.py`
- `apps/master_data/services.py`
- `apps/core/system_views.py`
- `apps/core/ui.py`
- `apps/timesheets/services.py`
- `apps/core/reports_views.py`
- `apps/core/ts_views.py`
- `apps/auth/policies.py` if Phase 2 oversight is approved
- related templates for system-management forms and collection grids

Expected test updates:

- `tests/test_system_management_ui.py`
- timesheet service and UI tests covering available projects and save/submit
- approval tests for cross-office project lines
- `tests/test_reports_ui.py`
- `tests/test_project_management_ui.py`
- transfer-blocker tests

## 12. Recommended Delivery Phases

### Phase 0. Spec Approval

Update current-source-of-truth docs to add:

- the new cross-office staffing concept
- explicit home-office calendar/GCC semantics
- project-office approval semantics
- project-time reporting semantics

### Phase 1. Schema And Management UI

- add model and migration
- add management service
- add `Cross-Office Staffing` collection/create/detail UI
- add audit events
- add transfer blockers

### Phase 2. Timesheet Engine

- add shared staffing eligibility helper
- update project-line validation
- update available-projects query
- add tests for origin-office holiday and target-office holiday behavior

### Phase 3. Project Staffing Views And Reports

- update project management counts
- update missing-timesheet logic
- update project-time reporting labels and filters as approved

### Phase 4. Optional Target-Office Admin Oversight

- redesign `TS_ADMIN` approval oversight for project-office visibility
- update `Pending Approvals` and `Approval Turnaround` if the business wants
  target-office admin visibility rather than home-BU visibility

## 13. Testing Blueprint

Minimum new tests:

- create valid cross-office staffing record
- reject same-office record in cross-office staffing flow
- reject inactive employee
- reject project/date window violations
- reject overlaps against both staffing models
- allow project line save when only cross-office staffing exists
- weekly available-project list includes cross-office staffed project
- origin-office holiday blocks project charge according to employee calendar
- target-office holiday still permits time according to origin-office calendar
- project-owner approval can see/action cross-office project time
- project-time report includes cross-office charged lines
- missing-timesheet report includes cross-office staffing windows
- employee transfer is blocked while active cross-office staffing exists

## 14. Main Risks

- duplicated union logic if the shared staffing helper is skipped
- unclear BU attribution in project reports if labels are not updated
- accidental scope leakage if employee-origin-office visibility is mixed with
  target-project authorization incorrectly
- later employee transfer can distort history unless origin-office context is
  stored explicitly
- UX friction if the create form uses a huge global employee selector

## 15. Recommendation

Build Option 4 only if the business wants a durable, explicit staffing model.

Recommended implementation stance:

- use a dedicated `CrossOfficeProjectAssignment` model
- keep home-office timesheet semantics unchanged
- align management and approval scope around the target project
- phase target-office `TS_ADMIN` oversight separately
- centralize eligibility in a shared staffing resolver before touching reports

This yields the cleanest long-term design while containing the first delivery
to the behavior you explicitly requested.
