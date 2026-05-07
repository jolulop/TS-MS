# Project Time Inquiry UI

## 1. Goal

Replace the deferred `Project Time Inquiry` TS Management placeholder with a live scoped inquiry screen for `PROJECT_OWNER` and `PROJECT_MANAGER`, reusing the existing project-time reporting backend.

## 2. Scope

In scope:
- turn `/ts/inquiry/` into a real inquiry screen
- reuse the existing project-time scoped dataset and filters
- keep project inquiry limited to project owners and project managers
- add UI tests for allowed and denied access

Out of scope:
- new report calculations
- export actions
- TS Admin-specific inquiry behavior under `/ts/`
- new API endpoints

## 3. Source documents

- `docs/TS MAnagement functional specification v.5.3.docx`
- `docs/UI - Screen Specification  v5.3.docx`
- `docs/Use cases - Acceptance criteria v5.3.docx`
- `docs/ui-screen-spec-v5.2.md`
- `AGENTS.md`

## 4. Current state

- `/reports/project-time/` already renders the scoped project-time report.
- `/ts/inquiry/` still renders a deferred placeholder card.
- TS navigation and dashboard copy still describe project inquiry as pending work.

## 5. Target behavior

- `PROJECT_OWNER` and `PROJECT_MANAGER` can open `/ts/inquiry/` and see the live project-time inquiry grid with filters and totals.
- Scope remains server-side and matches the existing project-time report rules.
- Regular users remain denied from `/ts/inquiry/`.
- The TS navigation copy no longer calls the feature a placeholder.

## 6. Affected areas

Backend modules:
- `apps/core`
- `apps/auth`

Frontend screens/features:
- TS Management inquiry screen
- navigation copy

Database / migrations:
- none

APIs:
- none

## 7. Tests

- update TS UI tests for inquiry visibility and access
- add inquiry page test covering real scoped content

## 8. Risks

- duplicating report rendering logic between `/reports/` and `/ts/inquiry/`
- accidentally broadening inquiry access beyond PO/PM
