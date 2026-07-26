# Product specifications

`feature-contract.json` is the machine-verifiable index of user-visible product
behavior. It complements, rather than replaces, detailed tests and API schemas.

Each feature has:

- a stable unique `id`;
- a category and behavior description;
- ordered acceptance steps;
- `passing` with executable repository evidence, or `planned` with a linked
  gap.

Update the contract in the same change as product behavior. Do not use
`passing` for an implementation that has no executable verification reference.
Run `make harness-static` after editing it.
