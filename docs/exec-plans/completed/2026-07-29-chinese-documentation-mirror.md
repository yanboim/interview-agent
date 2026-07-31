# Chinese documentation mirror

- Status: completed
- Date: 2026-07-29
- Owner: repository maintainers

## Objective

Provide a complete Simplified Chinese mirror for every current lifecycle
document listed in `docs/document-manifest.json`, while keeping source,
generated references, links, and future updates mechanically synchronized.

## Scope

- Mirror all current lifecycle documents under `docs/zh-CN/`.
- Reuse already-Chinese source content without semantic rewriting.
- Provide maintained Chinese translations for English narrative sources.
- Generate Chinese API, configuration, data-dictionary, and product-contract
  references from repository sources.
- Add a machine-readable source-to-Chinese mapping and Harness checks.

Historical completed execution plans, archived reports, and `knowledge/`
interview corpora are records or runtime content rather than current lifecycle
documentation and are not duplicated.

## Acceptance criteria

- Every path in `docs/document-manifest.json` has exactly one Chinese mirror.
- The Chinese index explains authority, layout, exclusions, and update policy.
- Relative links inside the Chinese mirror resolve.
- Generated Chinese references are reproducible and fail checks when stale.
- `make harness-static` and `make harness-check` pass.

## Progress

- [x] Current documentation inventory and language coverage measured.
- [x] Mirror layout and translation sources implemented.
- [x] All Chinese documents generated.
- [x] Manifest, links, and staleness checks implemented.
- [x] Full verification complete.

## Verification

Passed on 2026-07-29:

```text
make docs-check
  English generated references current
  Chinese documentation current: 118 documents
make harness-static
  17 passed
make harness-check
  backend: 224 passed, 2 skipped
  frontend unit: 18 passed
  frontend type/build/bundle: passed
make e2e
  24 passed
```

The first sandboxed browser attempt could not reach its loopback web server.
The first unsandboxed run had one transient desktop resume-title timing
failure while the identical mobile scenario passed; the immediate full rerun
passed all 24 browser cases.
