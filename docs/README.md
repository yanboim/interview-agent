# Repository documentation

This directory is the maintained knowledge base for Interview Agent. Start with
the task-oriented links below instead of reading every document.

## Start here

| Need | Read |
|---|---|
| Understand the product and run it locally | [Root README](../README.md) |
| Understand module and dependency boundaries | [Architecture](../ARCHITECTURE.md) |
| Set up a development environment and make a change | [Development guide](development.md) |
| Choose and run the right verification | [Testing guide](testing.md) |
| Check machine-verifiable product behavior | [Feature contract](product-specs/README.md) |
| Deploy, diagnose, back up, or recover the service | [Reliability and operations](reliability/README.md) |
| Review authentication, authorization, data, or secrets | [Security model](security/README.md) |
| Propose a durable architecture decision | [Design documents](design-docs/README.md) |
| Plan a non-trivial implementation | [Execution plans](exec-plans/README.md) |
| Check known structural limitations | [Technical-debt tracker](tech-debt-tracker.md) |
| Update or add documentation | [Documentation guide](documentation-guide.md) |

`AGENTS.md` is the concise entry map for coding agents. It points to this
knowledge base and defines mandatory repository gates.

## Information architecture

- `product-specs/`: machine-readable behavior and acceptance contracts.
- `design-docs/`: durable architectural decisions and design proposals.
- `exec-plans/`: active and completed implementation plans.
- `reliability/`: dependency behavior, operations, recovery, and runbooks.
- `security/`: trust boundaries, data handling, and security controls.
- `generated/`: reproducible references generated from code or schemas.
- `tech-debt-tracker.md`: prioritized architectural debt.

The root [README](../README.md) remains the product overview and operator quick
start. Detailed procedures belong here and should be linked from the root
README rather than duplicated.

## Authority and freshness

When sources disagree, use this order:

1. executable tests and database constraints;
2. `product-specs/feature-contract.json`;
3. `ARCHITECTURE.md` and accepted design documents;
4. operational and development guides;
5. historical plans, roadmaps, and evaluation reports.

The update triggers, ownership rules, and lifecycle for each document type are
defined in the [documentation guide](documentation-guide.md).
