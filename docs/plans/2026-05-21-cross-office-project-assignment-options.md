# Cross-Office Project Assignment Options

## 1. Goal

Enable an employee to be assigned to projects outside the employee's current
Office, with a clear understanding of the business-rule, authorization, and
timesheet implications.

## 2. Current Baseline

Current `v5.9.5` behavior is intentionally restrictive:

- project assignments are Business Unit scoped through the project
- the assigned employee must be active and in the project Business Unit scope
- project-assignment administration is enforced inside the caller's active
  Office scope
- cross-Office employee changes are currently modeled through the dedicated
  Employee Transfer workflow

Important implementation consequence:

- disabling the Project Assignment BU membership check alone does **not**
  complete cross-Office support
- timesheet charging still depends on the employee's weekly timesheet Business
  Unit, assigned calendar, and project assignment for the work date
- project lists and assignment-management selectors are also filtered by the
  user's active Office in multiple places

## 3. Design Options

### Option A. Keep assignment local and use Employee Transfer

Description:

- preserve the current model
- require a cross-Office Employee Transfer before the employee can work on the
  target Office's projects

Pros:

- minimal product and code risk
- keeps calendar, approval, reporting, and authorization semantics coherent
- fits the current source-of-truth docs and workflow

Cons:

- does not solve true dual-Office staffing
- transfer is too heavy if the employee must work across Offices at the same
  time

When to choose:

- if the real business need is permanent relocation rather than concurrent
  multi-Office staffing

### Option B. Allow cross-Office assignments but keep BU membership required

Description:

- allow a Project Assignment to reference an employee from another Office
- still require the employee to have active scope in the project's Business
  Unit
- extend employee BU scope so it can include Business Units from multiple
  Offices

Pros:

- strongest consistency with current "assignment implies BU membership" rule
- keeps reporting and approval semantics closer to the current model

Cons:

- large model and authorization change
- current employee model assumes one Office context for employee scope
- many validations and UI selectors assume all employee Business Units belong
  to the same Office
- likely requires revisiting employee administration, active Office semantics,
  and session context design

When to choose:

- only if BU membership is a mandatory governance concept even for
  cross-Office staffing

Implementation impact:

- employee BU-scope model and validations
- employee create/update and transfer flows
- assignment create/list/detail services
- auth session and active Office context rules
- report and query scoping that currently assumes same-Office relationships

### Option C. Allow cross-Office assignments and remove the BU-membership requirement for assignments

Description:

- allow a Project Assignment to reference an active employee from another
  Office
- remove the rule that the employee must already belong to the project's
  Business Unit scope
- treat the Project Assignment itself as the authorization basis for charging
  time to that project

Pros:

- smallest path that actually enables cross-Office staffing
- avoids redesigning employee BU scope across multiple Offices
- matches your stated tolerance that disabling the BU restriction could be OK

Cons:

- changes an existing core business rule
- requires careful handling of timesheet Business Unit, calendar-period-rule,
  and reporting semantics
- makes "assignment" and "BU membership" diverge, so some admin and audit
  interpretations become less intuitive

When to choose:

- when the business goal is to staff employees across Offices without moving
  their employee home Office or BU

Implementation impact:

- project assignment validation
- project-assignment employee selectors and queries
- timesheet project eligibility and validation
- clarification of which Business Unit owns the charged time when an employee
  works on another Office's project
- report wording and acceptance criteria

### Option D. Introduce explicit cross-Office staffing assignments

Description:

- keep normal Project Assignments as-is
- add a new assignment type or flag such as `cross_office_assignment`
- require extra governance fields such as source Office, target Office,
  effective dates, approval reason, and possibly a host Business Unit

Pros:

- cleanest long-term domain model
- preserves current local assignment rules for the normal path
- makes cross-Office staffing explicit and auditable

Cons:

- largest delivery scope
- more UI, model, reporting, and policy work than the other options

When to choose:

- if cross-Office staffing is strategic and expected to grow

Implementation impact:

- schema changes
- new validation and policy rules
- new UI affordances
- report and audit expansion

## 4. Required Business Decisions

Before implementation, the product needs explicit answers for:

1. Which Business Unit owns the timesheet?
   Current engine resolves many rules from the employee's timesheet Business
   Unit, not the project's Office alone.

2. Which calendar/day-limit rules apply?
   Current day limits come from the employee calendar plus a Business Unit
   period rule.

3. Which approval path should apply?
   Project approval currently follows the project/assignment path, but
   governance may differ for cross-Office staffing.

4. Which reports should count the employee under source Office, target Office,
   or project Office?

5. Should cross-Office staffing be allowed for all roles, or only by
   `TS_ADMIN_MASTER` / `TS_ADMIN` with extra audit?

## 5. Recommendation

Recommended path: **Option C** as the smallest viable way to satisfy the new
need.

Reasoning:

- it meets the stated business goal directly
- it avoids redesigning employee BU scope into a multi-Office model
- it keeps the employee's home Office and transfer workflow intact
- it can be delivered incrementally if we clearly redefine assignment as the
  source of project-charging eligibility, independent of project-BU membership

Recommended guardrails for Option C:

- keep employee active-status requirement
- keep project active/closed-date restrictions
- allow cross-Office assignment create/update only for `TS_ADMIN`
  initially
- add explicit audit text when assignment crosses Offices
- document how timesheet Business Unit, approval routing, and reporting should
  behave before implementation begins

## 6. Suggested Delivery Sequence For Option C

1. Approve the new business rule:
   assignment may cross Offices and does not require employee membership in the
   project Business Unit.

2. Decide the time-ownership rule:
   either employee-home-BU-owned time or project-BU-owned time.

3. Update validation and selectors for Project Assignment Management.

4. Update timesheet validation so eligible project charging follows the new
   assignment rule without breaking calendar/day-limit behavior.

5. Update reporting and acceptance docs.

6. Add focused tests for:
   - cross-Office assignment create
   - timesheet save/submit on cross-Office assigned project
   - approval visibility
   - report visibility and totals
