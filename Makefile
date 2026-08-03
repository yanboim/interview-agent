PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
NPM ?= npm
NPM_RUN ?= $(NPM) --silent --prefix frontend run
WORKTREE_ENV ?= .env.worktree
E2E_PORT ?= $(shell $(PYTHON) -m scripts.worktree_env --root . --value E2E_PORT)

.PHONY: help docs-generate docs-check eval-check production-preflight-check workflow-retirement-check workflow-prerelease-retirement-check dev-check pr-check harness-static backend-fast-check backend-check frontend-fast-check frontend-check migration-check e2e harness-check \
	worktree-env stack-config stack-up stack-down lock-python

help:
	@echo "make harness-static  Validate repository contracts and architecture"
	@echo "make docs-generate   Regenerate English references and Chinese mirror"
	@echo "make docs-check      Verify generated and Chinese documentation"
	@echo "make eval-check      Run the frozen deterministic Agent quality gates"
	@echo "make production-preflight-check  Validate Workflow V2 production release configuration"
	@echo "make workflow-retirement-check  Require approved Workflow V2 production evidence"
	@echo "make workflow-prerelease-retirement-check  Require approved pre-release acceptance evidence"
	@echo "make dev-check       Run the short local compile and static feedback loop"
	@echo "make pr-check        Run deterministic PR checks without browsers or images"
	@echo "make backend-check   Compile and run the backend test suite"
	@echo "make backend-fast-check  Run backend tests that need no external service"
	@echo "make frontend-check  Type-check, test, build, and enforce bundle budgets"
	@echo "make migration-check Validate migrations on a fresh isolated SQLite database"
	@echo "make e2e             Run Playwright browser acceptance tests"
	@echo "make harness-check   Run the complete local Harness verification gate"
	@echo "make worktree-env    Generate isolated Compose and E2E settings"
	@echo "make stack-config    Validate this worktree's Compose configuration"
	@echo "make stack-up        Start this worktree's isolated Compose stack"
	@echo "make stack-down      Stop this worktree's isolated Compose stack"
	@echo "make lock-python     Regenerate the Python 3.12 hash lock"

harness-static: docs-check eval-check
	$(PYTHON) -m pytest -q tests/test_architecture.py tests/test_harness_contract.py tests/test_reproducibility.py tests/test_structure_baseline.py

docs-generate:
	$(PYTHON) -m scripts.generate_docs
	$(PYTHON) -m scripts.generate_chinese_docs

docs-check:
	$(PYTHON) -m scripts.generate_docs --check
	$(PYTHON) -m scripts.generate_chinese_docs --check

eval-check:
	$(PYTHON) -m scripts.evaluate_agent_stack

production-preflight-check:
	$(PYTHON) -m scripts.check_production_preflight --require-workflow-v2

workflow-retirement-check:
	$(PYTHON) -m scripts.check_workflow_rollout

workflow-prerelease-retirement-check:
	$(PYTHON) -m scripts.check_workflow_prerelease

dev-check:
	$(PYTHON) -m compileall -q app scripts migrations
	$(PYTHON) -m pytest -q tests/test_architecture.py
	$(NPM_RUN) check:toolchain
	$(NPM_RUN) type-check

backend-check:
	$(PYTHON) -m compileall -q app scripts migrations
	$(PYTHON) -m pytest -q

backend-fast-check:
	$(PYTHON) -m compileall -q app scripts migrations
	$(PYTHON) -m pytest -q -m "not integration"

frontend-fast-check:
	$(NPM_RUN) check:toolchain
	$(NPM_RUN) type-check
	$(NPM_RUN) test:ci

frontend-check:
	$(MAKE) frontend-fast-check
	$(NPM_RUN) build:ci
	$(NPM_RUN) check:bundle

migration-check:
	$(PYTHON) -m scripts.check_migrations

e2e:
	E2E_PORT=$(E2E_PORT) $(NPM_RUN) test:e2e

pr-check: harness-static backend-fast-check frontend-check migration-check

harness-check: harness-static backend-check frontend-check e2e

worktree-env:
	$(PYTHON) -m scripts.worktree_env --root . --output $(WORKTREE_ENV)

stack-config: worktree-env
	docker compose --env-file .env --env-file $(WORKTREE_ENV) config --quiet

stack-up: worktree-env
	docker compose --env-file .env --env-file $(WORKTREE_ENV) up -d --build

stack-down: worktree-env
	docker compose --env-file .env --env-file $(WORKTREE_ENV) down

lock-python:
	docker run --rm -v $(CURDIR):/src -w /src python:3.12-slim@sha256:cab2dbf575e971934a81e4622f5aba17aa7929719bd7e31033a3a83b97fd0464 sh -c 'python -m pip install --disable-pip-version-check pip-tools==7.6.0 && python -m piptools compile --quiet --generate-hashes --resolver=backtracking --strip-extras --output-file=requirements.txt requirements.in'
	$(PYTHON) -m scripts.reproducibility stamp
	$(PYTHON) -m scripts.reproducibility check
