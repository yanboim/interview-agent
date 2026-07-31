# New engineer onboarding guide

- Status: completed
- Date: 2026-07-29
- Owner: repository maintainers
- Technical debt: none (documentation only)
- Product contract: none (documentation only)

## Objective

Provide a second onboarding document, `docs/ONBOARDING-GUIDE.md`, oriented as a
step-by-step tutorial (Day 1 → on-call ready) plus detailed reference appendices
(API/tables/env-var quick references, task cookbook, command and learning-path
cheat sheets). It complements the existing concise `ENGINEERING-HANDOVER-MANUAL.md`
(quick-reference, 14-section overview) and the `enterprise-agent-engineering-course.md`
(12-week general agent engineering course) without duplicating their forms.

## Non-goals

- Replace or delete `ENGINEERING-HANDOVER-MANUAL.md`.
- Copy generated content into the guide (API/config/data-dictionary stay linked
  to `docs/generated/` to avoid drift).
- Change any code, migrations, or configuration.
- Run live model/RAG evaluations (cost-bearing, out of scope).
- Touch `docs/generated/` or `docs/zh-CN/` (generated/maintained separately).

## Acceptance criteria

- `docs/ONBOARDING-GUIDE.md` exists and clearly states its relationship to the
  two existing onboarding/teaching documents at the top.
- Covers the three requested areas: development, operations, and usage.
- Commands and file paths are consistent with the actual repository (Makefile,
  Dockerfile, docker-compose.yml, app/main.py, app/database.py, scripts/).
- Does not inline generated references; links to them instead.
- Registered in `docs/README.md` "按角色进入" table with the role split noted.
- `make harness-static` passes (no documentation/contract/architecture breakage).

## Affected contracts and architecture rules

None directly. Documentation-only change. The guide reiterates existing
architecture gates (layered dependencies, `model_gateway` confinement,
`SyncExecutor` single boundary, Alembic-driven schema) by pointing at their
sources; it does not define new behavior.

## Implementation steps

1. Verify facts against the codebase: `.env.example` defaults, `app/database.py`
   table list (19 tables), `app/` and `frontend/src/` directory layout,
   Makefile targets, feature-contract categories.
2. Write `docs/ONBOARDING-GUIDE.md`:
   - Opening (relationship to other docs, source-of-truth priority).
   - Part 1 — step-by-step onboarding (Ch 1 system overview, Ch 2 Day 1 run it,
     Ch 3 Day 2-3 trace a request, Ch 4 week 1 first loop).
   - Part 2 — usage manual (Ch 5 user, Ch 6 admin, Ch 7 API caller).
   - Part 3 — operations and release (Ch 8 daily ops, Ch 9 release/rollback,
     Ch 10 troubleshooting table).
   - Appendices A-F (directory tree, env var groups, table quick-ref, cookbook,
     command cheat sheet, learning path).
3. Register in `docs/README.md` with the role split vs the existing handover
   manual and the engineering course.
4. Run `make harness-static` and record the result.

## Progress

- [x] Facts verified: 19 tables, env defaults, app/frontend layout, Makefile.
- [x] `docs/ONBOARDING-GUIDE.md` written (opening + Ch 1-10 + appendices A-F).
- [x] Fixed a non-existent file reference (`single_agent.py`) found during
      self-review; single-agent construction lives in `app/agent.py`.
- [x] Registered in `docs/README.md`.
- [x] Editing `docs/README.md` (a Chinese authoritative source) made the
      `docs/zh-CN/README.md` auto-mirror stale; regenerated it with
      `python -m scripts.generate_chinese_docs` (the documented workflow, not a
      hand-edit of the generated mirror).
- [x] Ran `make harness-static` → passed: docs-check current (generated + 118
      Chinese docs), and 17 architecture/harness/reproducibility tests passed.

## Decisions and unexpected findings

- A second onboarding doc was explicitly requested by the requester despite an
  existing handover manual. To avoid duplication and drift, the new doc is
  positioned as a tutorial + detailed-reference complement, with explicit role
  split documented in both `docs/README.md` and the guide's opening.
- Generated references (`api-routes.md`, `configuration.md`,
  `data-dictionary.md`) are linked, never copied, so the guide cannot drift
  from the code.
- The earlier-surveyed "active/2026-07-29-engineering-handover-manual.md" does
  not actually exist under `active/`; the handover manual was committed
  directly without a matching plan file. This plan does not retroactively
  create one for that prior work.

## Rollback / migration considerations

Documentation-only. Rollback is deleting `docs/ONBOARDING-GUIDE.md` and
reverting the `docs/README.md` table edit. No data, schema, or runtime impact.
