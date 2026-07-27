# Release closeout

- Status: completed
- Date: 2026-07-27
- Owner: repository maintainers

## Objective

Publish the deployed anonymous-observability authentication guard and its
production evidence to GitHub, then replace the default Grafana administrator
credential without exposing the replacement secret.

## Non-goals

- Expose Grafana or other infrastructure ports publicly.
- Commit `.env`, credentials, tokens, or generated backups.
- Change application authentication or authorization behavior.
- Rebuild or restart unrelated production services.

## Acceptance criteria

- The focused frontend regression test and repository Harness pass.
- Only the observability fix, regression test, deployment records, and this
  closeout record enter the Git change.
- A dedicated remote branch and draft pull request preserve the change.
- Grafana uses a generated strong credential stored only in the ignored
  production environment file.
- The old Grafana credential is rejected, the replacement authenticates, and
  Grafana remains bound to `127.0.0.1`.

## Progress

- [x] Confirm GitHub state and exact commit scope.
- [x] Verify, commit, push, and open a draft pull request.
- [x] Rotate and verify the Grafana administrator credential.
- [x] Record non-secret evidence and complete final checks.

## Evidence

- Branch: `agent/anonymous-observability-auth-guard`.
- Implementation commit: `831848f` (`guard anonymous observability events`).
- Draft pull request: `#14`, targeting `main`.
- Focused observability regression: 1 test passed.
- Harness static gate: 14 tests passed.
- The exact deployed runtime tree previously passed the full Harness: 154
  backend tests with 2 optional external-service skips, 11 frontend tests,
  frontend type/build/bundle gates, and 10 Playwright tests.
- Grafana rotation used `grafana cli admin reset-admin-password
  --password-from-stdin`; no replacement credential was included in command
  output, Git, or deployment records.
- The generated credential is stored only in ignored `.env`, which remains
  mode 0600. The temporary secret and pre-rotation environment copy were
  removed after successful verification.
- The old credential returned 401, the replacement returned 200, and Grafana
  remained restricted to `127.0.0.1:3000`.

## Rollback

For the code change, revert the dedicated commit through the normal review
workflow. For Grafana, retain the local environment file backup until the new
credential has been verified. If rotation fails, restore only the prior
Grafana credential setting and recreate only the Grafana service; do not remove
the `grafana_data` volume.
