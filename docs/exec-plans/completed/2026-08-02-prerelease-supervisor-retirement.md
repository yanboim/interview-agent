# Pre-release Workflow V2 acceptance and Supervisor retirement

- Status: completed
- Date: 2026-08-02
- Owner: project owner and repository maintainers

## Objective

Retire the nested Supervisor before the product's first public release without
pretending that a low-traffic private environment has production observation
data. Keep the existing production 24-hour/100-completion comparison gate for
future public rollout and introduce a separate, fail-closed pre-release gate.

## Non-goals

- Do not weaken or relabel the production observation gate.
- Do not use synthetic traffic as production traffic.
- Do not retain prompts, answers, private knowledge, credentials, or raw logs in
  acceptance evidence.
- Do not remove the single-agent mode used when multi-agent support is disabled.
- Do not delete historical release, metric, prompt, schema, or model provenance.

## Acceptance criteria

1. The deterministic application-stack report passes at least 230 cases with
   zero privacy, authorization, fabricated-source, or confirmation failures.
2. A live isolated cohort passes at least six requests, covers knowledge,
   interviewer, evaluator, and planner, and includes at least two multi-intent
   requests. Evidence is sanitized and the exact test identity is removed.
3. The currently deployed app and worker are immutable image IDs and match a
   successful release-ledger entry.
4. The previous Supervisor-capable app and worker image tarballs have recorded
   SHA-256 digests and the matching rollback exercise is `rolled_back`.
5. The project owner approves the completed evidence after the live cohort.
6. `make workflow-prerelease-retirement-check` passes before compatibility code
   is removed.
7. Contracts, topology, tests, runbooks, technical debt, and rollback guidance
   describe the resulting explicit Workflow V2 runtime.
8. Focused checks and `make harness-check` pass; the final image is built,
   vulnerability-scanned, deployed, and verified before completion.

## Ordered work

- [x] Define the distinct pre-release policy, template, CLI, Make target, and
  focused tests.
- [x] Bind deterministic evidence and immutable current/rollback artifacts.
- [x] Run and precisely clean the isolated live-model acceptance cohort.
- [x] Obtain project-owner approval of the completed sanitized evidence.
- [x] Pass the pre-release retirement gate.
- [x] Remove nested Supervisor routing and expose explicit Workflow V2 topology.
- [x] Update contracts, runbooks, tests, and debt/progress records.
- [x] Run the full Harness, build and scan final images, deploy, and verify.

## Decisions and findings

- The private environment has no representative organic traffic, so generating
  100 synthetic requests would validate load mechanics but not production user
  outcomes. It is not accepted as production evidence.
- The original production gate remains a separate public-launch safeguard. Its
  retained-Supervisor and Workflow V2 windows each remain at least 24 hours and
  100 completed requests with external approval.
- The pre-release path trades traffic comparison for broader deterministic
  coverage, a bounded live cohort, zero-tolerance safety checks, precise cleanup,
  immutable artifacts, a verified rollback exercise, and explicit owner signoff.
- The first live cohort stopped on an Interviewer `ModelBudgetExceeded`: four
  calls per structured, tool-capable specialist were insufficient in the real
  provider path. The failed identity and its orphaned failed turn were deleted
  by exact IDs and verified at zero. The bounded per-route call allowance is now
  five; shared 16K-token, cost, and 90-second limits remain unchanged.
- The accepted r5 cohort passed 6/6 live requests with two multi-intent cases,
  all four specialists, sanitized evidence, and exact identity cleanup. The
  project owner approved that completed evidence before the fail-closed gate
  returned `workflow_prerelease_gate=approved` against the production ledger.
- The final Supervisor-free r6 image is
  `sha256:6b1432d0a26f8943da46d087ffa2a68851259ebac5e5eabde9d0153a20c416a5`.
  Its app and worker tar SHA-256 values are respectively
  `28a293ccd38d773b3422ea5dad51a47d1b98402554d0889d788893124de5fe4c`
  and `4b75bddc92e6d4baeafd15719ee3cd9312693cd411a5f0c7270cc99e4eaf19ce`.
  The pinned Trivy scan found zero fixable HIGH/CRITICAL findings in both.
- Canonical code gates passed: five Agent groups at 1.0, 29 static/architecture
  tests, 332 backend tests with two explicit external-service skips, 23
  frontend unit tests, type/build/bundle checks, and 28 browser scenarios. The
  first browser attempt was invalidated by restricted local-socket/Chromium
  startup failures; the complete isolated single-worker rerun passed 28/28.
- Production release
  `production-workflow-v2-supervisor-free-20260802-6b1432d0-r6` is `succeeded`.
  App and worker use the final image, health/readiness are 200, runtime topology
  is `workflow_v2` with no Supervisor key, and a real evaluator+interviewer
  smoke passed. The exact smoke trace/user were deleted and users, tokens,
  conversations, turns, messages, and traces all verified at zero.

## Rollback

After Supervisor source removal, changing a runtime flag is not a rollback.
Load and redeploy the recorded previous app and worker image tarballs, verify
their SHA-256 digests, run health/readiness and an isolated smoke test, and
record a new rollback release entry. No database migration is expected.
