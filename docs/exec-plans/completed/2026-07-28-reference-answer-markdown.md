# Reference answer Markdown rendering

- Owner: repository maintainers
- Status: completed 2026-07-28
- Next action: deploy the verified frontend change and monitor reference-answer
  rendering in production.

## Objective

Render interview reference answers as readable Markdown even when a model
returns compact, single-line numbered sections and bullets.

## Non-goals

- Change persisted historical answers.
- Apply heuristic rewriting to general chat messages or code blocks.
- Permit unsafe HTML.

## Acceptance criteria

- Reference answers use the shared sanitized Markdown renderer.
- A reference-answer-only normalizer repairs surrounding emphasis whitespace
  and introduces conservative list boundaries in compact model output.
- Numbered sections, bullets, bold text, and inline code render without visible
  Markdown delimiters.
- Existing chat Markdown behavior and sanitization remain unchanged.
- Unit, browser, and repository checks pass.

## Risks and rollback

- Over-aggressive normalization could alter prose. Rules are scoped to reference
  answers and require explicit numbered/bold or sentence/bullet patterns.
- The change is frontend-only and can be rolled back without data migration.

## Progress

- [x] Rendering path and screenshot inspected.
- [x] Normalizer and component integration implemented.
- [x] Regression verification complete.

## Verification evidence

- Focused frontend unit tests: 14 passed.
- Frontend type check and production build passed.
- Interview engine tests: 2 passed.
- Focused Playwright coverage: desktop and mobile passed.
- Full `make harness-check`: 186 backend tests passed, 2 skipped; 14 frontend
  unit tests passed; 16 desktop/mobile browser tests passed.
