# Dev Seed Timesheet Submit Fix

## Problem

The local developer sample data creates active General Charge Codes with
`requires_approval_flag=True`, but the current implementation only supports
project-scoped approval routing. Submitting a sample timesheet that mixes project
and General Charge Code lines therefore rolls back with no state transition.

## Scope

- fix the dev sample data so seeded General Charge Codes are compatible with the
  currently implemented approval workflow
- add regression coverage proving a seeded-style timesheet can be submitted and
  routed into the approval UI

## Notes

- this is a data/bootstrap fix, not a change to the current approval model
- current behavior for true General Charge Code approval remains unchanged until
  that workflow is explicitly implemented
