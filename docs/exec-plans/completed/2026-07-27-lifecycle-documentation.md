# Full lifecycle documentation

- Status: completed
- Date: 2026-07-27
- Owner: repository maintainers

## Objective

Create a coherent P0 documentation set spanning product definition, prototype
and interaction design, system architecture, software delivery, quality,
release, operations, and security. Refocus the root README on orientation and
quick start while preserving detailed information through canonical links.

## Non-goals

- Change application behavior, product scope, infrastructure, or schemas.
- Produce polished visual design assets or a hosted interactive prototype.
- Claim planned product outcomes, SLOs, privacy commitments, or recovery
  targets as already approved.
- Modify unrelated frontend observability or release-closeout work already in
  progress.

## Acceptance criteria

- Product vision, PRD, personas, journeys, feature map, and non-functional
  requirements distinguish current behavior from proposed direction.
- Information architecture, user flows, screen inventory, prototype
  specification, and interaction-state contracts cover critical product paths.
- Architecture documents cover system context, containers, components, domain,
  data, agent, and RAG behavior with links to executable evidence.
- Delivery documents define lifecycle, readiness, done, review, test strategy,
  acceptance, and quality gates.
- Release, rollback, environments, operations, incident, backup, disaster
  recovery, threat model, classification, and privacy documents exist.
- Root and documentation indexes route readers to canonical material.
- Required-document and internal-link Harness checks pass.

## Work plan

1. Inventory current implementation, contracts, tests, deployment, and active
   work.
2. Add the product, UX, architecture, and SDLC documentation.
3. Add quality, release, operations, and security documentation.
4. Refocus README and documentation navigation; classify historical reports.
5. Extend Harness requirements, run static verification, and archive this plan.

## Progress

- [x] Repository sources and current worktree changes inventoried.
- [x] Product, UX, architecture, and SDLC documents complete.
- [x] Quality, release, operations, and security documents complete.
- [x] Entry points and historical material organized.
- [x] Static Harness passes.

## Verification

```bash
make harness-static
```

The task is documentation-only. Runtime suites are not required unless a
documentation assertion or generated reference depends on runtime behavior.

Result on 2026-07-27: `make harness-static` passed with 14 tests. This covered
required documents, all repository-internal Markdown links, feature-contract
traceability, architecture rules, and reproducible build inputs.

## Decisions and findings

- The documentation follows one lifecycle from product intent and prototype to
  architecture, delivery, quality, release, operations, and security.
- The root README was reduced to product orientation, quick start, primary
  commands, production requirements, and canonical links. Detailed procedures
  now have one owner under `docs/`.
- `DEVELOPMENT_ROADMAP.md`, `P0_P2_COMPLETION.md`, and `plan.md` were initially
  kept at the repository root for link stability but explicitly classified as
  historical. They were later relocated into `docs/history/` (see
  `2026-08-03-archive-historical-docs.md`); that newer plan supersedes this
  decision.
- `ARCHITECTURE.md` still described atomic knowledge publication and durable
  Redis jobs as unresolved; it was corrected to match the implemented and
  tested state.
- Formal SLO/RPO/RTO values, legal privacy commitments, high-fidelity visual
  design, and a hosted interactive prototype are intentionally not invented.
  The documents identify these as approval-dependent follow-up work.
- Existing unrelated worktree changes were preserved.

## Rollback

Revert the new document directories, navigation changes, and required-document
assertions together. Do not revert unrelated files that predate this plan.
