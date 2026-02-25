PYTHON := python3
VENV := .venv
VENV_PY := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff
PYTEST := $(VENV)/bin/pytest

.PHONY: help setup install-dev lint test format run clean

help:
	@echo "Targets:"
	@echo "  make setup       Create .venv and install dev dependencies"
	@echo "  make install-dev Install project + dev deps into existing .venv"
	@echo "  make lint        Run Ruff lint checks"
	@echo "  make format      Auto-fix lint issues where possible"
	@echo "  make test        Run test suite"
	@echo "  make run         Show zoom CLI help"
	@echo "  make clean       Remove caches"

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PY) -m pip install --upgrade pip setuptools wheel
	$(VENV_PIP) install -e ".[dev]"

install-dev:
	$(VENV_PIP) install -e ".[dev]"

lint:
	$(RUFF) check .

format:
	$(RUFF) check . --fix

test:
	$(PYTEST)

run:
	./zoom --help

clean:
	/bin/rm -rf .pytest_cache .ruff_cache
