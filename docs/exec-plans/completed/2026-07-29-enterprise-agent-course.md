# Enterprise Agent engineering course

- Status: completed
- Date: 2026-07-29
- Owner: repository maintainers

## Objective

Create a beginner-friendly Chinese course that teaches how to understand,
build, test, secure, operate, and evolve an enterprise-grade Agent by using the
current Interview Agent repository as a running case study.

## Non-goals

- Replace the repository's architecture, security, quality, or operations
  documents.
- Introduce a new Agent framework or change production behavior.
- Claim that a multi-agent topology is inherently more reliable than a
  well-bounded single agent.
- Run cost-bearing live model or RAG evaluations.

## Acceptance criteria

- The course clearly distinguishes an LLM call, an Agent, an agentic product,
  and Codex as a development assistant.
- The material progresses from a minimal loop through tools, RAG, persistence,
  reliability, security, evaluation, observability, deployment, and
  multi-agent orchestration.
- Every module contains learning goals, repository reading, a hands-on
  exercise, and an executable or inspectable completion criterion.
- The course maps important claims to current repository files and product
  contracts.
- The course includes a realistic study schedule, capstone project, debugging
  method, and a definition of production readiness.
- Repository documentation checks pass, or any unavailable check and its exact
  dependency are reported.

## Implementation plan

1. Inspect architecture, product contracts, technical debt, Agent code, tools,
   model gateway, evaluations, security, quality, and operations documents.
2. Cross-check current Agent terminology and design guidance against official
   OpenAI sources.
3. Write the Chinese course as a standalone repository document.
4. Validate Markdown structure and repository documentation rules.
5. Move this plan to `completed/` after verification.

## Progress

- [x] Architecture and repository guide inspected.
- [x] Agent, tools, model gateway, routing evaluation, security, quality, and
  operations examples inspected.
- [x] Current official Agent guidance reviewed.
- [x] Course written.
- [x] Documentation verification complete.

## Verification evidence

- A structural audit found 23 lessons, 23 learning-goal sections, 23
  repository-reading sections, 23 exercises, and 23 inspectable acceptance
  sections.
- All 21 relative Markdown links in the course resolve to existing repository
  paths.
- The course contains 1,499 lines and 23 consistently structured lessons,
  each with learning goals, repository reading, a hands-on exercise, and an
  inspectable acceptance criterion. It also covers the capstone,
  production-readiness checklist, and first-week schedule.
- `make docs-check` passed, including generated-document and all 118
  Chinese-document currency checks.
- `make harness-static` passed with 17 architecture, contract, and
  reproducibility tests.
- `make harness-check` passed: 228 backend tests passed with 2 intentional
  skips; 18 frontend unit tests passed; frontend type-check, production build,
  and bundle budgets passed; and all 24 desktop/mobile browser E2E tests passed.
- An attempted `tests/test_docs.py` check was not applicable because that test
  file does not exist; the repository's documented `make docs-check` target was
  used as the authoritative documentation gate.

## Decisions and findings

- The course uses the repository's existing provider-neutral concepts. OpenAI
  documentation is used for current terminology and general design guidance,
  while the production code currently uses a Zhipu-compatible model endpoint.
- The curriculum starts with a single agent. Multi-agent orchestration is
  delayed until routing failures and responsibility boundaries can be measured.
- Enterprise readiness is taught as a system property covering deterministic
  software, data, security, evaluation, and operations, not as a prompt-writing
  technique.

## Rollback

This is a documentation-only change. Remove the course document and this plan
if the material is rejected; no runtime or data migration rollback is needed.
