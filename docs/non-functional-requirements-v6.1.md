# Non-Functional Requirements v6.1

## 1. Security

- all post-login authorization is internal
- production authentication must use a trusted external identity claim boundary
  rather than browser-posted email values
- local development email login must be disabled when
  `TSMS_ENVIRONMENT=production`
- server-side authorization is mandatory
- deny by default
- do not rely on hidden UI actions for security

## 2. Data Integrity

- use forward-only migrations for schema changes
- preserve referential integrity
- prefer guarded deletes over destructive cascades
- enforce business constraints in backend services

## 3. Auditability

- sensitive administrative and workflow actions must emit audit events
- audit should capture actor, target, action, and before/after details where relevant

## 4. Consistency

- UI and backend validations must agree
- Office and Business Unit scope must be applied consistently across UI, API, and reports
- shared System Management create and edit screens should follow the same layout direction where implemented

## 5. Usability

- server-rendered admin screens should provide direct create/edit flows
- detail pages are the main update surface
- collection tables should use clear primary-row navigation without requiring a duplicate visible action column
- blocked actions should return clear user-facing errors

## 6. Maintainability

- business logic should stay in services and policies, not in thin controllers/views
- reusable authorization rules should stay centralized
- markdown repository docs should remain aligned with the implemented code

## 7. Observability

- audit and integration job history must remain reportable
- administrative failures should surface stable error codes or clear UI messages
