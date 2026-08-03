# Claim citation Markdown rendering

- Owner: product frontend
- Status: completed
- Completed: 2026-08-03

## Objective

Render claim-level citations as safe, readable Markdown instead of exposing
raw blockquote, list, emphasis, and inline-code delimiters.

## Non-goals

- Change citation generation, evidence validation, or persisted citation data.
- Apply citation-specific normalization to the main chat answer.
- Permit raw model-generated HTML.

## Acceptance criteria

- Citation claims use the shared DOMPurify-backed Markdown renderer.
- Citation-only normalization repairs common closing-emphasis whitespace and
  removes an orphan trailing double-backtick marker.
- Blockquotes, lists, emphasis, and inline code render without visible raw
  delimiters while evidence status remains visible.
- Citation Markdown cannot activate unsafe HTML.
- Component/unit and desktop/mobile browser regression coverage pass.
- Repository release gates pass.

## Outcome

- `ChatPanel` routes each citation claim through `MarkdownContent` after
  citation-scoped normalization.
- Citation blockquotes, nested lists, emphasis, and inline code use compact,
  scoped styles without changing the main answer typography.
- The browser sidebar uses the public `/health` liveness probe; the operator-only
  `/ready` dependency probe remains protected by the deployment key.
- The AI-quality feature contract records the persisted and streamed rendering
  behavior and its executable verification.
- Focused unit/component tests, desktop/mobile Playwright coverage,
  `make pr-check`, and `make harness-check` pass.

## Risks and rollback

- Block Markdown inside citation items changes their internal DOM structure;
  styles remain scoped to the citation list.
- The change is frontend-only and can be rolled back without data migration.

## Progress

- [x] Screenshot and rendering path inspected.
- [x] Safe rendering and scoped styles implemented.
- [x] Regression coverage complete.
- [x] Product contract, generated documentation, and release gates complete.
