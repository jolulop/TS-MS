# Phase 5 UI Shell And Navigation

## 1. Goal

Establish the first real user-facing HTML shell for the TS system with role-aware top-level navigation, a dashboard/home experience, and the shared page structure that later System Management and TS Management screens will reuse.

## 2. Scope

In scope:
- server-rendered app shell and shared layout primitives
- role-aware top-level menu visibility
- access entry page for local/manual session initialization
- dashboard / home page
- access denied page
- user profile / session context page
- top-level placeholder pages for:
  - System Management
  - TS Management
  - Approval Worklist
  - Reports
- UI integration tests for shell visibility and access control

Out of scope:
- CRUD forms and data grids for business entities
- full timesheet editor UI
- approval decision UI
- report filters and report data rendering
- frontend JavaScript application shell

## 3. Source documents

- `docs/UI - Screen Specification  v5.1.docx`
- `docs/Authorization Matrix aligned to Functional Specification v5.1.docx`
- `docs/TS MAnagement functional specification v.5.1.docx`
- `AGENTS.md`
- `PLANS.md`

Note:
- The repository currently contains the approved spec documents as `.docx` files under `docs/`, not the markdown filenames referenced in `AGENTS.md`. This plan uses the current files present in the repo.

## 4. Current state

- The project has a minimal placeholder home page only.
- Internal session initialization, backend authorization, and Phase IV backend workflows are implemented.
- There are no real server-rendered application pages for authenticated users yet.
- There is no role-aware menu shell.

## 5. Target behavior

After Milestone 1:
- unauthenticated users see an access-entry page suitable for local development
- authenticated users land on a dashboard shell
- the application header shows user/session context
- the navigation reflects internal TS roles only
- unauthorized pages render an Access Denied screen
- the top-level functional areas are visible and navigable even where later milestones still provide placeholder content

## 6. Affected areas

Backend modules:
- `apps/core`
- `apps/auth`
- `config`
- `tests`

Frontend screens/features:
- access entry
- access denied
- dashboard / home
- user profile / session context
- top-level navigation shell
- placeholder overview pages for future Phase 5 milestones

Database / migrations:
- none expected

APIs:
- no API contract changes expected

Jobs / integrations:
- none

## 7. Business rules impacted

- UI menus and pages are shown based on internal TS roles only
- unauthorized menus are hidden
- direct URL access to unauthorized pages shows Access Denied
- backend authorization remains authoritative

## 8. Authorization impact

Roles affected:
- `USER`
- `TS_ADMIN`
- `PROJECT_OWNER`
- `PROJECT_MANAGER`

Scope affected:
- self dashboard/profile scope
- role-based menu visibility only in this milestone

Planned shell visibility:
- Home: all authenticated users
- TS Management: all authenticated users
- System Management: `TS_ADMIN`, plus `PROJECT_OWNER` for limited project-management-oriented access
- Approval Worklist: `PROJECT_MANAGER` only in this milestone
- Reports: all authenticated users, as a placeholder only

## 9. Data model changes

- migration needed: no
- tables affected: none
- reference data seed changes: none
- backfill needed: no

## 10. API changes

- none expected for Milestone 1
- local access-entry page may reuse existing internal session initialization services server-side

## 11. UI changes

Screens to add/change:
- access entry / session initialization page
- access denied page
- dashboard / home
- profile / session context page
- system management overview placeholder
- TS management overview placeholder
- approval worklist placeholder
- reports placeholder

Shared shell work:
- authenticated header
- role-aware navigation
- common page card/list/metadata styling

## 12. Audit and logging impact

- reuse existing login-identification audit through current auth services
- no new audit event types expected

## 13. Milestones

### Milestone 1
- app shell and menus by role
- access entry and dashboard
- access denied and profile/session context
- top-level placeholder pages for future UI milestones

### Milestone 2
- System Management screens
  - employee list and detail/edit
  - client list and detail/edit
  - internal category list and detail/edit
  - cost center list and detail/edit
  - general charge code list and detail/edit
  - calendars and project-management screens remain deferred

### Milestone 3
- TS Management screens

### Milestone 4
- approval worklist UI

### Milestone 5
- reports UI

## 14. Test plan

Integration tests:
- unauthenticated user sees access-entry screen
- authenticated user sees dashboard and own session context
- role-aware menu visibility by role
- unauthorized direct URL access shows Access Denied
- limited System Management visibility for Project Owner

## 15. Risks and mitigations

- Risk: UI menu rules drift from backend authorization.
  - Mitigation: keep visibility logic narrow and mirror backend role rules conservatively.
- Risk: Milestone 1 accidentally grows into full entity-screen work.
  - Mitigation: use placeholder overview pages for future sections instead of implementing CRUD screens now.

## 16. Rollout / deployment notes

- feature flag needed: no
- backward compatibility: existing APIs remain unchanged

## 17. Open questions / assumptions

- Assumption: local development can use a simple server-rendered access-entry form that submits a validated email into the existing internal session initialization flow.
- Assumption: Milestone 1 uses top-level navigation and overview placeholders rather than full submenu trees for all future screens.
- Assumption: `PROJECT_OWNER` gets visibility of the System Management block in Milestone 1 because the authorization matrix gives limited system/project-management access there.
- Assumption: `PROJECT_MANAGER` gets Approval Worklist visibility, while TS Admin approval oversight remains deferred.
- Assumption: Milestone 2 covers the TS Admin-managed screens already backed by services in the repo today: employees and the classification masters. Calendar and project-management screens stay out of this milestone to keep the rollout small and consistent with existing backend coverage.

## 18. Definition of done

- plan file created and tracked in `PLANS.md`
- shell pages implemented
- role-aware navigation implemented
- tests added/updated
- validations run and passing

## 19. Implementation status

Status:
- in progress

Completed milestone:
- Milestone 1: shell and role-aware navigation
- Milestone 2: System Management screens for employees and classification masters

Still pending:
- Milestone 3: TS Management screens
- Milestone 4: approval worklist UI
- Milestone 5: reports UI

Validation completed for Milestone 1:
- `make format`
- `make lint`
- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py makemigrations --check`
- `.venv/bin/python manage.py migrate`
- `make test`
- `make format-check`

Validation completed for Milestone 2:
- `make format`
- `make lint`
- `.venv/bin/python manage.py check`
- `.venv/bin/python manage.py makemigrations --check`
- `.venv/bin/python manage.py migrate`
- `make test`
- `make format-check`
