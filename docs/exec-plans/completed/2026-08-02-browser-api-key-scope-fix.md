# Browser API key scope fix

- Status: completed
- Date: 2026-08-02
- Owner: repository maintainers

## Objective

Restore product and administrator browser login without exposing the shared
deployment API key. Keep the key on the server-only readiness probe and retain
Bearer identity, role, ownership and rate-limit controls for browser APIs.

## Acceptance criteria

- Product registration/login, administrator login and authenticated browser APIs
  do not require `X-API-Key`.
- `/ready` still rejects a missing or invalid deployment key.
- Security contract, operator documentation and Chinese mirror match runtime.
- Focused tests and the canonical Harness pass.
- A scanned immutable image is deployed; user and administrator login are
  verified through the production gateway without retaining test identities.

## Work

- [x] Isolate the API-key path policy and add a regression test.
- [x] Update the security contract and operator documentation.
- [x] Run documentation, focused and complete gates.
- [x] Build, scan, deploy and record the release.
- [x] Verify both login surfaces, exact cleanup, health and readiness.

## Completion evidence

- Canonical Harness: 334 backend passed with 2 explicit external-service skips;
  23 frontend unit tests and 28 browser E2E tests passed; static,
  architecture, documentation and Agent gates passed.
- Immutable app/worker image:
  `sha256:a5a55750f9b70d646fc035bbbe9a1c72b4b2dbb743b76af47c3a4bc7405edbc4`.
- Fixed-digest Trivy scans of both exported image archives passed with zero
  HIGH/CRITICAL Debian and Python findings under `--ignore-unfixed`.
- Production release
  `production-browser-api-key-scope-fix-20260802-a5a55750f9b7-r7` reached
  `succeeded`; app is healthy and app/worker run the same immutable image.
- Production-gateway smoke proved product and administrator login without
  `X-API-Key`, Bearer identity and administrator authorization, `/ready` 401
  without the deployment key and 200 with it. Both temporary identities were
  located uniquely, deleted by exact `user_id` plus username, and all related
  counts were verified zero.
- The build initially exposed that `.var/` and `backups/` were entering the
  Docker context. They are now excluded alongside IDE and test runtime output;
  the resulting context was 10.89 MB and contained no release archives or
  database backups.
