# Profile avatar and reminder controls

- Owner: product frontend/backend
- Status: completed
- Next action: none.

## Objective

Make the sidebar account identity stable at every supported viewport, let a
user upload or remove their avatar from settings, and replace the malformed
reminder checkbox with a compact accessible switch.

## Non-goals

- Avatar cropping or a general-purpose media library.
- Push-notification delivery changes.
- Admin account profile customization.

## Acceptance criteria

- The avatar never shrinks or clips when account actions are visible.
- The avatar is discoverable as a settings action and accepts JPEG, PNG, or
  WebP images, resized client-side before account-scoped persistence.
- Removing an avatar restores a centered two-character fallback.
- The reminder control has switch semantics, a compact visual size, keyboard
  operation, and no inherited full-width input styling.
- Desktop and mobile settings layouts have no horizontal overflow.

## Contracts and architecture

- Add an optional `avatar_data_url` to `user_profiles` through Alembic.
- Add a user-owned `/api/profile/avatar` write adapter; ownership continues to
  be resolved by the server.
- Keep image validation at the API boundary and persistence in storage.

## Implementation

1. Add avatar schema, migration, storage operation, route, and API tests.
2. Add frontend profile API/state support and an upload/remove settings UI.
3. Stabilize the sidebar footer layout and reminder switch styling.
4. Add browser coverage, update the feature contract, and run repository gates.

## Decisions and findings

- Store a small normalized data URL in the profile row. The browser crops and
  resizes to 256 px; the API independently validates type, encoding, and size.
  This keeps the avatar account-scoped without introducing mutable container
  filesystem state.
- The reminder bug was caused by `.interview-form input { width: 100% }`
  overriding the checkbox inside `.inline-check`.
- Chromium invalidates the selected image if the file input is cleared before
  asynchronous decoding completes. The implementation now reads the file
  first and resets the input only in the completion path.
- This work resolves product bugs and creates no new architectural debt, so the
  technical-debt register remains unchanged per its product-bug policy.

## Rollback and migration

- The migration is additive and nullable. Rollback removes only
  `avatar_data_url`; existing account and training data is unaffected.

## Verification

- `make harness-check`
  - 176 backend tests passed, 2 skipped.
  - 13 frontend unit tests passed.
  - Production build and bundle budgets passed.
  - 12 Playwright cases passed across desktop and mobile Chromium.
- Focused avatar schema, storage, and migration suite: 21 passed.
