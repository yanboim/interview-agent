# Documentation guide

## Purpose

Documentation is part of the change, not a follow-up artifact. It should let a
maintainer identify current behavior, its evidence, operational consequences,
and the next safe action without reconstructing intent from source history.

## Document types

| Document | Owns | Update when |
|---|---|---|
| `README.md` | Product overview, quick start, primary operator entry points | Setup, supported workflows, or top-level commands change |
| `ARCHITECTURE.md` | Runtime context, module boundaries, correctness rules | Dependencies or a correctness boundary changes |
| `product-specs/feature-contract.json` | Verifiable user-visible behavior and status | Behavior or its executable evidence changes |
| `design-docs/*.md` | Durable technical decisions and consequences | A significant decision is proposed, accepted, replaced, or rejected |
| `exec-plans/active/*.md` | Work in progress, decisions, and verification | Non-trivial work advances or encounters a finding |
| `exec-plans/completed/*.md` | Historical implementation and verification record | A plan meets its acceptance criteria |
| `reliability/` | Dependency failure behavior, operations, recovery | Runtime topology, health checks, backup, rollback, or alerting changes |
| `security/` | Trust boundaries and security invariants | Auth, authorization, secrets, external data flow, or exposure changes |
| `product/` | Vision, users, PRD, scope, business rules, and NFRs | Product intent, scope, rules, or success criteria change |
| `ux/` | Information architecture, journeys, prototype, and states | Navigation, page scope, interaction, or user recovery changes |
| `architecture/` | Current system, domain, data, Agent, RAG, and API design | Components, ownership, protocols, or data flows change |
| `sdlc/` | Readiness, implementation, review, and completion process | Delivery governance or review gates change |
| `quality/` | Test strategy, acceptance, and quality gates | Verification scope or release evidence changes |
| `release/` | Environments, deployment, and rollback | Packaging, migration, promotion, or rollback changes |
| `operations/` | Day-2 operations, incident, backup, and DR | Operational procedure or recovery behavior changes |
| `project/` | Milestones, risks, decisions, responsibilities, and status | Cross-domain scope, ownership, or delivery risk changes |
| `tech-debt-tracker.md` | Prioritized recurring boundary problems | Debt is found, reprioritized, completed, or superseded |
| `generated/` | Reproducible references only | Its source changes and the generator is run |

Source comments explain local intent and constraints. They do not replace
repository documentation for cross-module behavior.

## Required metadata

Execution plans include status, date, owner or responsible role, objective,
non-goals, acceptance criteria, progress, verification, and rollback.

Design documents include context, decision, alternatives or rejected options,
consequences, migration where relevant, and verification. If a decision is not
yet implemented, say so explicitly and link its active plan or technical debt.

Runbooks state prerequisites, safe checks, action steps, expected result,
rollback, and escalation conditions. Never place real credentials, user data,
private knowledge text, or database dumps in documentation.

## Lifecycle

1. Update documentation in the same change as behavior.
2. Keep active plans in `exec-plans/active/` and record findings as work
   proceeds.
3. Mark product behavior `passing` only when every verification reference
   exists and executes the claimed behavior.
4. Move a plan to `exec-plans/completed/` only after its acceptance criteria
   pass. Preserve decisions and failed approaches.
5. Replace stale content instead of appending contradictory notes. For
   superseded design documents, add a visible status and a link to the new
   decision.

## Writing and linking

- Describe current behavior in the present tense and target behavior as
  planned.
- Use repository-relative links so they work locally and in code review.
- Link to a single source of truth instead of copying configuration tables or
  command sequences into multiple files.
- Put commands in copyable fenced blocks and state when they are destructive,
  cost-bearing, credential-dependent, or require an external service.
- Prefer executable evidence: tests, migrations, evaluation datasets, or
  generated output with a regeneration command.
- Keep secrets as placeholders. `.env.example` documents configuration names;
  `app/config.py` remains the implementation source of truth.

## Review checklist

- Does the document distinguish implemented, planned, and historical behavior?
- Are commands correct from the repository root?
- Do internal links resolve?
- Are security and destructive-operation warnings explicit?
- Does changed behavior update its feature contract, design record, runbook,
  or debt entry as appropriate?
- Does `make harness-static` pass?

## Automated completeness

`docs/document-manifest.json` lists the required corpus by lifecycle stage.
`tests/test_harness_contract.py` verifies every entry exists and is unique.
API routes, Settings, and relational metadata are generated with:

```bash
python -m scripts.generate_docs
python -m scripts.generate_docs --check
```

Generated-reference drift fails the Harness static gate.
