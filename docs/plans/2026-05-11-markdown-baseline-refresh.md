# Markdown Baseline Refresh

## 1. Goal

Bring the repository markdown files to a clean current baseline before a fresh environment restart so repo-level guidance, development notes, and specification links all reflect the implemented v5.4 Django system.

## 2. Scope

In scope:
- repo-level markdown guidance files
- documentation indexes and development notes
- superseded-status clarification for older markdown deltas
- plan index updates

Out of scope:
- non-markdown source files
- legacy `.docx` documents
- behavior changes in application code

## 3. Source Documents

- `docs/specification-index-v5.4.md`
- `docs/functional-spec-v5.4.md`
- `docs/ui-screen-spec-v5.4.md`
- `docs/integration-api-spec-v5.4.md`
- `docs/authorization-matrix-v5.4.md`
- `docs/business-rules-catalog-v5.4.md`
- `docs/use-cases-acceptance-v5.4.md`
- `docs/data-model-erd-v5.4.md`
- `docs/non-functional-requirements-v5.4.md`
- `AGENTS.md`

## 4. Affected Files

- `README.md`
- `AGENTS.md`
- `PLANS.md`
- `docs/specification-index-v5.4.md`
- `docs/architecture/stack.md`
- `docs/development/local-setup.md`
- `docs/development/reference-data-strategy.md`
- `docs/database-schema-diagram.md`
- `docs/functional-spec-v5.2.md`
- `docs/ui-screen-spec-v5.2.md`
- `docs/integration-api-spec-v5.2.md`

## 5. Changes

- replace outdated v5.1 and v5.2 source-of-truth references with v5.4 references
- align repo-level stack guidance to the implemented Django monolith
- align setup and seed notes to the current Makefile and sample data
- refresh the spec index summary with calendar and weekend-hours changes
- clearly mark older v5.2 markdown notes as historical only

## 6. Verification

- review markdown files for internal consistency
- run `git diff --check`

## 7. Risks

- repo guidance drift if future code changes are not reflected in markdown
- older historical plan documents still describe past milestones by design, so this refresh focuses on current guidance rather than rewriting completed history
