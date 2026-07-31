# Resume analysis timeout reliability

- Owner: repository maintainers
- Status: completed 2026-07-29

## Objective

Recover production resume assessment from repeated model read timeouts without
loosening latency behavior for interactive chat. Give the offline resume
analysis purpose an explicit timeout and retry policy, then verify an existing
queued production assessment completes.

## Non-goals

- Change the production model, provider, prompt, or resume content.
- Read or expose uploaded resume text.
- Enable audio transcription or change unrelated feature flags.

## Acceptance criteria

- Resume analysis uses a purpose-specific timeout instead of the global
  interactive timeout.
- Provider-internal retries are disabled for resume analysis because the
  durable job queue already provides bounded retries.
- Chat and other model purposes retain the existing global timeout/retry
  settings.
- Configuration reference, environment example, and regression tests are
  updated.
- Full repository checks pass.
- Production Worker receives the new settings; in-flight work is allowed to
  finish before replacement and the latest queued analysis reaches `ready`.

## Findings

- The failing document extracts to 6,758 characters, below the 60,000-character
  application budget.
- Production used the default 45-second model timeout and two provider retries.
  Each durable job attempt therefore waited approximately 136 seconds before
  the queue scheduled another attempt.
- Multiple attempts reached `APITimeoutError`; parsing, storage, database,
  Redis, and Worker heartbeat remained healthy.

## Progress

- [x] Production failure and input size diagnosed without reading content.
- [x] Purpose-specific configuration and tests implemented.
- [x] Full quality gate passed.
- [x] Production configuration deployed and queued assessment recovered.
- [x] Release outcome recorded.

## Verification evidence

- Focused gateway, resume-engine, resume-service, and Worker tests: 18 passed.
- Full repository Harness: 219 backend tests passed with 2 environment-gated
  skips, 18 frontend unit tests passed, and 22 desktop/mobile browser tests
  passed.
- The production Python 3.12 image reports a resume-analysis timeout of 180
  seconds and zero provider-internal retries; the global interactive settings
  remain unchanged.
- The App was replaced first while the old Worker completed its in-flight job.
  The latest two production analyses reached `ready` before the Worker was
  replaced, so no active lease was interrupted.
- Final App image:
  `sha256:8c2cc3e37d597c2527636857297c1a692f679a2f27255112008965bf18248cc0`;
  Worker image:
  `sha256:ffe0f7ba25a18f7079ffef49db85b0200d3d01c0515490a8014b2495ea434708`.
- Health, readiness, new Worker heartbeat, zero restart counts, and
  deployment-window logs passed.
- Release ledger:
  `production-20260729T030704Z | 2026.07.29.0311 | production | succeeded |
  20260729_0016`.
