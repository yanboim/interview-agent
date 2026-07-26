PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
NPM ?= npm

.PHONY: help harness-static backend-check frontend-check e2e harness-check

help:
	@echo "make harness-static  Validate repository contracts and architecture"
	@echo "make backend-check   Compile and run the backend test suite"
	@echo "make frontend-check  Type-check, test, build, and enforce bundle budgets"
	@echo "make e2e             Run Playwright browser acceptance tests"
	@echo "make harness-check   Run the complete local Harness verification gate"

harness-static:
	$(PYTHON) -m pytest -q tests/test_architecture.py tests/test_harness_contract.py

backend-check:
	$(PYTHON) -m compileall -q app scripts migrations
	$(PYTHON) -m pytest -q

frontend-check:
	$(NPM) --prefix frontend run type-check
	$(NPM) --prefix frontend test
	$(NPM) --prefix frontend run build
	$(NPM) --prefix frontend run check:bundle

e2e:
	$(NPM) --prefix frontend run test:e2e

harness-check: harness-static backend-check frontend-check e2e
