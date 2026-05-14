# General Charge Code Role-Based Approvals

## Goal

Enable approval-required General Charge Codes to participate in the timesheet
approval workflow by routing them to either:

- existing internal TS roles such as `PROJECT_MANAGER` or `TS_ADMIN`
- office-scoped ad-hoc approval roles created only for General Charge Code
  approvals

The chosen approval mode is option 1: any eligible employee can approve a routed
General Charge Code approval item, and the first decision wins.

## Scope

In scope:

- master data for office-scoped ad-hoc General Charge Code approval roles
- employee membership assignment for those ad-hoc roles
- General Charge Code approver-role configuration
- System Management CRUD UI and admin JSON endpoints for ad-hoc approval roles
- submit/list/detail/approve/reject approval flow updates for approval-required
  General Charge Code lines
- approval worklist and pending-approvals reporting alignment
- tests and spec documentation updates

Out of scope:

- changing the Employee management UI for ad-hoc role memberships
- changing non-General-Charge-Code approval routing semantics

## Design

### Data model

- add `GeneralChargeCodeApprovalRole` as an office-scoped ad-hoc role master
- add `GeneralChargeCodeApprovalRoleAssignment` to map employees to active ad-hoc
  approval roles
- add `GeneralChargeCodeApproverRole` to map a General Charge Code to one or
  more approver roles, where each mapping points to either:
  - an existing `ROLE_CODE` reference value, or
  - an ad-hoc General Charge Code approval role
- add `ApprovalItemApproverRole` to snapshot the eligible role set when a
  General Charge Code approval item is created
- relax `ApprovalItem.approver_employee` so project approvals can still use it
  while General Charge Code approvals rely on role eligibility

### Workflow

- creating or updating a General Charge Code with `requires_approval_flag=True`
  requires at least one configured approver role
- approval-required General Charge Codes become available in the timesheet
  editor once they have valid routing
- submitting a timesheet creates:
  - one approval item per managed project as today
  - one approval item per approval-required General Charge Code used in the
    timesheet, with a snapped eligible-role set
- any employee matching one of the snapped roles can approve or reject the GCC
  approval item, except the timesheet owner
- the first approval or rejection closes that approval item; a rejection still
  cancels the remaining pending items in the submission cycle

### UI

- add a new System Management section for `General Charge Code Approval Roles`
- support create, edit, delete, and employee membership assignment there
- extend the General Charge Code create/edit forms to select approver roles from
  both:
  - existing system roles
  - office ad-hoc General Charge Code approval roles

## Risks

- approval authorization must stay server-side and must not rely on UI
- deleting ad-hoc roles must be guarded if approval items still reference them
- snapshot behavior must keep pending approvals stable if a GCC or ad-hoc role
  is edited after submission

## Verification

- model and service tests for routing and authorization
- HTML UI tests for the new System Management flows
- approval worklist/detail tests for GCC approval items
- `manage.py check`
- targeted pytest slices for master data, timesheets, approvals, and UI
