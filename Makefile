PY ?= .venv/bin/python
UV ?= uv

.PHONY: install fmt lint typecheck test test-all schemas check

install:  ## create/refresh the dev environment
	$(UV) pip install -p $(PY) -e ".[dev]"

fmt:  ## auto-format and fix safe lint issues
	$(PY) -m ruff format src tests
	$(PY) -m ruff check --fix src tests

lint:  ## lint + format check (no changes)
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests

typecheck:
	$(PY) -m mypy

test:  ## fast tests only (no data package, no Ollama)
	$(PY) -m pytest -m "not integration and not ollama" --cov --cov-report=term-missing:skip-covered

test-all:  ## everything, incl. tests that read the package data or call Ollama
	$(PY) -m pytest

schemas:  ## regenerate JSON schemas for the shared files (UI reads these)
	$(PY) -m pets_transformer.cli schemas --out schemas

check: lint typecheck test  ## run before every push
