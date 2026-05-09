# Use Cases And Acceptance v5.4

## 1. Office Bootstrap

### Use Case

`TS_ADMIN_MASTER` creates a new Office and makes it immediately manageable.

### Acceptance

- Office is created
- Office configuration is created
- bootstrap Business Unit is created in that Office
- bootstrap admin employee is created in that Office
- bootstrap admin employee is assigned to the bootstrap Business Unit

## 2. Office Configuration Inheritance

### Use Case

`TS_ADMIN_MASTER` updates Office configuration and Business Units inherit it.

### Acceptance

- Office detail allows configuration edit
- Business Unit detail shows inherited values read-only
- timesheet runtime behavior reads the inherited values

## 3. Client Management

### Use Case

`TS_ADMIN` creates and updates Office-level Clients.

### Acceptance

- Client creation does not require a Business Unit
- Client belongs to active Office
- Parent Client, if present, is in the same Office

## 4. Cost Center Management

### Use Case

`TS_ADMIN` creates and updates Office-level Cost Centers.

### Acceptance

- Cost Center creation does not require a Business Unit
- Cost Center belongs to active Office

## 5. Pricing Model Management

### Use Case

`TS_ADMIN` maintains Pricing Models for the active Office.

### Acceptance

- create Pricing Model with name and description
- update Pricing Model
- guarded delete succeeds when no project references exist
- guarded delete fails when a project still references the Pricing Model

## 6. Project Creation

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

## 7. Project Assignment Creation

### Use Case

`TS_ADMIN` assigns an employee to a Project.

### Acceptance

- employee is active
- employee is in project Business Unit scope
- project is not closed
- assignment window respects project dates

## 8. Employee Self-Service Timesheet

### Use Case

An authenticated employee edits and submits a weekly timesheet.

### Acceptance

- only one timesheet exists per employee/week
- lines are limited to valid weekdays
- line target is Project xor General Charge Code
- submit is blocked when validation fails

## 9. Approval Workflow

### Use Case

A Project Manager processes approval items.

### Acceptance

- approval worklist is visible to `PROJECT_MANAGER`
- only assigned approval items are actionable
- approve and reject actions are audited

## 10. Project Time Inquiry

### Use Case

A Project Owner or Project Manager views live project time.

### Acceptance

- inquiry screen is available to `PROJECT_OWNER` and `PROJECT_MANAGER`
- only owned or managed project scope is visible

## 11. Guarded Deletes

### Use Case

An admin deletes a transient master record from System Management.

### Acceptance

- delete succeeds when no protected references exist
- delete fails with an error when references still exist
- no cascade business delete occurs
