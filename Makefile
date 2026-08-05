UV ?= uv
VENV ?= .venv
PYTHON := $(VENV)/bin/python
DEV_PACKAGES := mypy==1.15.0 pytest==8.3.5 ruff==0.9.10 types-PyYAML==6.0.12.20241230
DATA_PACKAGES := PyYAML==6.0.2 datasets==3.2.0

.PHONY: install install-full lint test record-environment

install:
	$(UV) venv --allow-existing $(VENV)
	$(UV) pip install --python $(PYTHON) --no-deps --editable ./third_party/open-r1 --editable .
	$(UV) pip install --python $(PYTHON) $(DATA_PACKAGES)
	$(UV) pip install --python $(PYTHON) $(DEV_PACKAGES)

install-full:
	$(UV) sync --extra dev

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
	$(PYTHON) -m mypy src tests

test:
	$(PYTHON) -m pytest

record-environment:
	$(PYTHON) -m code_verifier.cli record-environment --output environment.json
