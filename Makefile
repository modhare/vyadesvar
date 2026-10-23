# Targets:
#   make test       default checks (stdlib only) — run on every push/PR in CI
#   make test-e2e   optional Playwright browser smoke tests
#   make test-all   both
PYTHON ?= python3

.PHONY: all test test-e2e test-all
all: test

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_site.py' -v

test-e2e:
	$(PYTHON) -m unittest discover -s tests/e2e -p 'test_*.py' -v

test-all: test test-e2e
