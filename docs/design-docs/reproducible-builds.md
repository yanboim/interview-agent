# Reproducible build inputs

## Python

`requirements.in` declares direct compatibility intent. `requirements.txt` is
a generated CPython 3.12 Linux lock containing exact transitive versions and
artifact hashes. Runtime, CI, and release builds install it with
`pip --require-hashes`; they never resolve the broad input file directly.

The lock header includes `requirements.in`'s SHA-256. The repository verifier
checks the header, exact pins, hashes, Dockerfile install command, and CI install
commands without network access.

## Images

Every external Dockerfile and Compose image reference has both a readable,
non-`latest` version tag and an OCI Linux/amd64 manifest digest. A digest change
is therefore visible in review even if an upstream tag is moved. Production
currently targets Linux/amd64; another architecture requires its own reviewed
digest set.

## Update workflow

1. Edit direct intent in `requirements.in` or select a reviewed image version.
2. Regenerate the Python lock in the documented Python 3.12 environment.
3. Stamp and run the offline reproducibility verifier.
4. Review direct and transitive version/hash or image digest changes.
5. Run dependency audits and `make harness-check`.

Dependabot may propose updates, but does not bypass these gates.
