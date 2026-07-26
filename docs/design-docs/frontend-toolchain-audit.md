# Frontend toolchain audit gate

## Baseline

The reviewed developer baseline is Vite 8, `@vitejs/plugin-vue` 6, vue-tsc 3,
and Vitest 4 on Node 20.19 or newer. Both the root declaration and
`package-lock.json` resolved package must meet the baseline.

## Gates

`frontend/scripts/check-toolchain.mjs` reads package metadata without contacting
the registry and fails if a required package is absent, resolved below the
reviewed major, or inconsistent with the lockfile. It runs as part of
`make frontend-check`.

CI additionally runs the full npm audit at `moderate` severity, including
developer dependencies. This is intentionally stricter than the prior `high`
threshold because the original six findings were build-time dependency
warnings.

`@vue/test-utils` remains exactly pinned at 2.2.7. Its unrelated 2.4.11 update
introduces a `js-beautify` dependency chain with six high-severity audit
findings, so it is deliberately excluded from this Vite/vue-tsc upgrade.

## Scope

Build-time packages do not enter the Python runtime image after the frontend
build stage. They still affect source transformation and developer machines, so
their versions, integrity values, tests, and audit state remain release inputs.
