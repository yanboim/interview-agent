# Interview question readability

- Status: completed
- Date: 2026-07-26
- Owner: repository maintainers
- Next action: monitor normal production usage for unexpected long-question
  formats.

## Objective

Make long interview questions readable and render the safe inline Markdown
emphasis emitted by the model without exposing syntax markers.

## Non-goals

- Change question-generation prompts or persisted interview data.
- Enable block Markdown, remote images, or executable HTML in question titles.
- Deploy to production without separate authorization.

## Acceptance criteria

- Desktop question text is between 20 and 24 CSS pixels with at least 1.5 line
  height; mobile text is 19 pixels.
- Long questions do not create horizontal overflow.
- Emphasis and inline code render semantically while raw `**` markers disappear.
- Question HTML remains sanitized and cannot introduce images or event handlers.
- Frontend checks and desktop/mobile Playwright acceptance pass.

## Architecture and security

- Rendering remains a frontend presentation concern.
- Inline model output passes through DOMPurify with an explicit tag and
  attribute allowlist.
- No backend, database, or API contract changes are required.

## Progress

- [x] Add allowlisted inline Markdown rendering.
- [x] Apply readable long-form question typography.
- [x] Add unit and browser regression coverage.
- [x] Run verification and record evidence.

## Verification evidence

`make harness-check` passed on 2026-07-26:

- Harness architecture and contract checks: 6 passed.
- Backend suite: 88 passed, 1 external-service test skipped.
- Frontend unit suite: 9 passed.
- Frontend type-check, production build, and bundle budgets: passed.
- Playwright desktop/mobile acceptance suite: 10 passed.

The dedicated browser regression verified 19–24 px computed question text,
line-height of at least 1.5, semantic emphasis and inline code, removal of raw
Markdown markers, and no horizontal overflow on both supported viewports.

An existing Today-card assertion was made deterministic by waiting for its
asynchronously loaded heading before reading computed line-clamp styles.

## Production release

Deployed with explicit authorization on 2026-07-26:

- App image:
  `sha256:7c5aa74f48058bf49c75fc2a0615597bfa28a06d8d674d03ebeb5ac73e0df364`
- Previous App rollback tag:
  `interview-agent-app:rollback-20260726T0745Z`
- Worker and all data-service containers were left unchanged.
- No database backup was added because this release contains no schema,
  persistence, API, or Worker changes.
- Alembic remained at `20260725_0007 (head)`.
- Data counts remained at 3 users, 6 conversations, 12 messages, and 5
  interviews.
- Production `/health` and `/ready` returned 200 and the App became healthy.
- Production HTML referenced the new `index-CsZ8umhn.css` and
  `index-DLgFS7bp.js` assets.
- Desktop/mobile production smoke passed with no error overlay, horizontal
  overflow, unexpected console errors, page errors, or response errors.

## Rollback

Restore the previous interpolation and question CSS. No stored data or schema
is changed.
