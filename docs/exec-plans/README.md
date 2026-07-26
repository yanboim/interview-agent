# Execution plans

Create an execution plan for work that spans multiple modules, changes a
correctness boundary, introduces a dependency, or cannot be completed and
verified in one short session.

An active plan records:

- objective and non-goals;
- acceptance criteria;
- affected contracts and architecture rules;
- ordered implementation steps;
- progress and verification evidence;
- decisions and unexpected findings;
- rollback or migration considerations.

Keep work-in-progress plans in `active/`. Move them to `completed/` only after
the acceptance criteria and required verification pass. Do not erase decisions
or failed approaches when completing a plan.
