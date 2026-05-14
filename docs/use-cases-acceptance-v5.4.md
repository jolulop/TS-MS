# Use Cases And Acceptance v5.4

## 1. Country Management

### Use Case

`TS_ADMIN_MASTER` creates, updates, and guarded-deletes Countries used by Offices.

### Acceptance

- Country create requires unique Country code and Country name
- Country detail allows status updates
- guarded delete succeeds when no Office references the Country
- guarded delete fails when one or more Offices still reference the Country

## 2. Office Bootstrap

### Use Case

`TS_ADMIN_MASTER` creates a new Office and makes it immediately manageable.

### Acceptance

- Office creation requires selecting an existing Country
- Office is created
- Office configuration is created
- bootstrap Business Unit is created in that Office
- bootstrap admin employee is created in that Office
- bootstrap admin employee is assigned to the bootstrap Business Unit

## 3. Office Configuration Inheritance

### Use Case

`TS_ADMIN_MASTER` updates Office configuration and Business Units inherit it.

### Acceptance

- Office detail allows configuration edit
- Business Unit detail shows inherited values read-only
- timesheet runtime behavior reads the inherited values

## 4. Client Management

### Use Case

`TS_ADMIN` creates and updates Office-level Clients.

### Acceptance

- Client creation does not require a Business Unit
- Client belongs to active Office
- Parent Client, if present, is in the same Office

## 5. Cost Center Management

### Use Case

`TS_ADMIN` creates and updates Office-level Cost Centers.

### Acceptance

- Cost Center creation does not require a Business Unit
- Cost Center belongs to active Office

## 6. Pricing Model Management

### Use Case

`TS_ADMIN` maintains Pricing Models for the active Office.

### Acceptance

- create Pricing Model with name and description
- update Pricing Model
- guarded delete succeeds when no project references exist
- guarded delete fails when a project still references the Pricing Model

## 7. Calendar Management

### Use Case

`TS_ADMIN` manages a Yearly Calendar and its Special Days inside System Management.

### Acceptance

- create Yearly Calendar inside the active Office without assigning a Business Unit
- open Calendar detail and browse the month view
- create Calendar Period Rules by selecting a Business Unit inside the shared Office calendar
- allow overlapping Calendar Period Rules for different Business Units
- reject overlapping Calendar Period Rules inside the same Business Unit
- save Working On Saturdays and Working On Sundays flags plus their max-hours on a Calendar Period Rule
- delete Calendar Period Rules when no protected references exist
- create Special Day with date and type
- update Special Day date or type
- delete Special Day when no protected references exist
- guarded delete fails with an error when a Calendar still has protected dependencies

## 8. Project Creation

### Use Case

`TS_ADMIN` creates a new Project.

### Acceptance

- Pricing Model is mandatory
- Project Owner must hold `PROJECT_OWNER`
- Project Manager must hold `PROJECT_MANAGER`
- Client belongs to the same Office
- Cost Center belongs to the same Office
- Pricing Model belongs to the same Office
- Internal Category belongs to the same Business Unit

### Additional Acceptance

- guarded delete succeeds when no assignments, timesheet lines, approval items, or other protected references exist
- guarded delete fails when dependent records still reference the Project

## 9. Project Assignment Creation

### Use Case

`TS_ADMIN` assigns an employee to a Project.

### Acceptance

- employee is active
- employee is in project Business Unit scope
- project is not closed
- assignment window respects project dates

### Additional Acceptance

- guarded delete succeeds when no protected references exist

## 8A. General Charge Code Management

### Use Case

`TS_ADMIN` maintains General Charge Codes in scoped Business Units.

### Acceptance

- create and update a General Charge Code with mandatory Cost Center, lifecycle, and validity fields
- require at least one approver role when `Requires Approval` is enabled
- reject create or edit when Cost Center is empty
- guarded delete succeeds when no timesheet lines, approval items, or other protected references exist
- guarded delete fails when dependent records still reference the General Charge Code

## 8B. General Charge Code Approval Role Management

### Use Case

`TS_ADMIN` maintains office-scoped ad-hoc approval roles used only for General Charge Code approvals.

### Acceptance

- create and update an ad-hoc approval role with member employees from the active Office
- existing TS internal roles are selectable on General Charge Codes but are not editable in this screen
- guarded delete fails when General Charge Codes or approval history still reference the ad-hoc role

## 9. Employee Self-Service Timesheet

### Use Case

An authenticated employee edits and submits a weekly timesheet.

### Acceptance

- only one timesheet exists per employee/week
- lines are limited to chargeable working dates for the week
- weekend lines are allowed only when the active Business Unit Calendar Period Rule enables them
- weekend daily limits use the configured Saturday/Sunday max-hours from the active Calendar Period Rule
- active Special Days override working weekends and remain non-working
- line target is Project xor General Charge Code
- submit is blocked when validation fails

## 10. Approval Workflow

### Use Case

An eligible approver processes routed approval items.

### Acceptance

- approval worklist is visible to:
  - `PROJECT_MANAGER` for directly assigned project approvals
  - any employee matching the configured roles on a General Charge Code approval item
- only assigned project items or role-matched General Charge Code items are actionable
- General Charge Code approval uses first-decision-wins behavior
- approve and reject actions are audited

## 11. Project Time Inquiry

### Use Case

A Project Owner or Project Manager views live project time.

### Acceptance

- inquiry screen is available to `PROJECT_OWNER` and `PROJECT_MANAGER`
- only owned or managed project scope is visible

## 12. Guarded Deletes

### Use Case

An admin deletes a transient master record from System Management.

### Acceptance

- delete succeeds when no protected references exist
- delete fails with an error when references still exist
- no cascade business delete occurs

## 13. TS Admin Business Unit Scope Synchronization

### Use Case

`TS_ADMIN` scope stays aligned with all Business Units in the active Office so Business Units cannot become orphaned.

### Acceptance

- creating a new Business Unit assigns it to every active `TS_ADMIN` employee in the same Office
- creating an employee with `TS_ADMIN` assigns all Business Units in that Office to the employee scope
- adding `TS_ADMIN` to an existing employee expands the employee scope to all Business Units in that Office
- saving Business Unit scope for an employee who still has `TS_ADMIN` may change the primary Business Unit but keeps the full Office Business Unit scope

## 14. Business Unit Code Reuse Across Offices

### Use Case

`TS_ADMIN` creates a Business Unit in one Office using a code that already exists in a different Office.

### Acceptance

- creation succeeds when the duplicate code exists only in another Office
- creation fails when the duplicate code already exists in the active Office
