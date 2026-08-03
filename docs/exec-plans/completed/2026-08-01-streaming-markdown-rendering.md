# Streaming Markdown rendering

Owner: frontend engineering
Status: completed
Completed: 2026-08-01

## Objective

Replace repeated full-document Markdown parsing for an in-progress chat answer
with a streaming-aware Vue renderer while preserving the existing trusted,
sanitized renderer for completed and non-chat Markdown.

## Non-goals

- Change the chat transport or backend streaming protocol.
- Redesign message-list virtualization or scrolling.
- Change interview-question and reference-answer rendering.

## Acceptance criteria

- An in-progress assistant answer uses `markstream-vue` with streaming-safe
  parsing and bounded rendering options.
- A completed answer continues to render headings, tables, highlighted code,
  and sanitized HTML through the existing renderer.
- Ending the stream performs one final render through the existing highlighted,
  sanitized renderer.
- Component tests, type checking, and the frontend production build pass.

All acceptance criteria are satisfied.

## Architecture and contract impact

This is a frontend rendering dependency only. It does not change persistence,
authorization, chat lifecycle, transport, or model-call boundaries. The
existing `conversation-persistence` and `durable-chat-turn-lifecycle`
contracts remain unchanged.

## Implementation and decisions

- Added and locked `markstream-vue` for active assistant output.
- Retained the chat store's existing `requestAnimationFrame` token coalescing.
- Kept completed and non-chat Markdown on the existing `marked` + DOMPurify
  path to preserve highlighted code blocks and the established safety boundary.
- Configured safe HTML policy, parse coalescing, a bounded live-node window,
  and viewport-priority rendering for active output.
- Loaded Markstream through an async child component only while generation is
  active, so its larger runtime and stylesheet do not enter ordinary initial
  route chunks.
- Displayed a safe plain-text fallback while the streaming-only chunk loads,
  avoiding a blank first response without interpreting model HTML.

## Unexpected findings

The Markstream runtime produces a 651.04 kB minified shared chunk (212.50 kB
gzip) and a 108.77 kB stylesheet (16.61 kB gzip). Both are isolated behind the
streaming-only dynamic import. The repository bundle budgets still pass.

## Verification

- `npm test -- --run src/components/MarkdownContent.test.ts`: 6 passed.
- `make frontend-check`: toolchain baseline, type check, 23 unit tests,
  production build, and bundle budgets passed.

## Rollback

Restore `MarkdownContent.vue` to its static renderer-only implementation,
delete `StreamingMarkdownContent.vue`, and remove the dependency and lockfile
entries. No data migration is involved.
