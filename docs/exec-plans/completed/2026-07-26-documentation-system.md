# Documentation system refresh

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers

## Objective

Turn the repository documentation skeleton into a navigable, maintainable
knowledge base that tells contributors where authoritative information lives,
how to develop and verify changes, and how to operate and secure the service.

## Non-goals

- Change application behavior, deployment topology, or database schema.
- Restate every API shape that is already available from OpenAPI.
- Claim verification or operational guarantees that are not backed by the
  repository.

## Acceptance criteria

- `docs/README.md` provides audience- and task-oriented navigation.
- Documentation ownership, status, update triggers, and review rules are
  explicit.
- Development and testing workflows are documented outside the root README.
- Reliability and security documentation describe current behavior, known
  limitations, and relevant executable evidence.
- Root entry points link to the expanded documentation without breaking the
  existing quick start.
- Harness tests check the new required documentation and internal Markdown
  links.
- Focused documentation checks pass.

## Work plan

1. Inventory current documentation, repository commands, configuration, tests,
   and operational scripts.
2. Add documentation conventions plus development and testing guides.
3. Expand reliability and security documentation from placeholders into
   current-state references.
4. Update the documentation index and root README links.
5. Extend the Harness contract and run focused checks.

## Progress

- [x] Existing documentation structure and mandatory repository context read.
- [x] Documentation content updated.
- [x] Focused checks pass.
- [x] Plan moved to `completed/`.

## Verification

Run:

```bash
make harness-static
```

This task does not change runtime code, so backend, frontend, and browser suites
are not required unless static checks reveal an implementation dependency.

Result on 2026-07-26: 7 tests passed. The gate verified architecture rules,
feature-contract traceability, required documents, and internal Markdown links.

## Decisions and findings

- The root README remains the product overview and quick start. Detailed
  contributor, testing, security, and operations material now has one canonical
  location under `docs/`.
- Documentation maintenance rules are enforced at the traceability floor:
  required files must exist and internal repository links must resolve.
- The root README described readiness as SQLite plus Qdrant. The implementation
  checks the configured database, Qdrant, and Redis when enabled, so the
  operational wording was corrected.
- Git worktree status could not be inspected because the provided `.git`
  directory was empty. Changes were therefore restricted to documentation and
  its Harness contract test.

## Rollback

The change is documentation-only. Revert the new guides, navigation changes,
and matching Harness assertions together so the required-document list remains
consistent with the repository.
