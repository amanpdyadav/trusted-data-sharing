PY ?= .venv/bin/python
UV ?= uv
PKG ?= TRUSTED_PETS_PROVING_GROUND_2026
CODE = src tests evaluation

.PHONY: install fmt lint typecheck test test-all schemas check baseline validate detect-score

install:  ## create/refresh the dev environment (+ the organisers' pets-eval toolkit for evaluation)
	$(UV) pip install -p $(PY) -e ".[dev]"
	@if [ -d "$(PKG)/toolkit" ]; then $(UV) pip install -p $(PY) -e "$(PKG)/toolkit"; \
	else echo "note: $(PKG)/toolkit not found; evaluation commands need it"; fi

fmt:  ## auto-format and fix safe lint issues
	$(PY) -m ruff format $(CODE)
	$(PY) -m ruff check --fix $(CODE)

lint:  ## lint + format check (no changes)
	$(PY) -m ruff check $(CODE)
	$(PY) -m ruff format --check $(CODE)

typecheck:
	$(PY) -m mypy

test:  ## fast tests only (no data package, no Ollama)
	$(PY) -m pytest -m "not integration and not ollama" --cov --cov-report=term-missing:skip-covered

test-all:  ## everything, incl. tests that read the package data or call Ollama
	$(PY) -m pytest

schemas:  ## regenerate JSON schemas for the shared files (UI reads these)
	$(PY) -m pets_transformer.cli schemas --out schemas

check: lint typecheck test  ## run before every push

# ---------------------------------------------------------------- validation (needs the data package)
baseline:  ## score the package quickstart output: our measured 'before'
	$(PY) -m evaluation baseline

validate:  ## score a release: make validate RELEASE=out/health/release ROWMAPS=out/health/private [SCENARIO=HEALTH-S1]
	$(PY) -m evaluation validate --release $(RELEASE) --rowmaps $(ROWMAPS) --scenario $(or $(SCENARIO),HEALTH-S1) --gate

detect-score:  ## score a detection file: make detect-score DETECTION=out/health/detection.json
	$(PY) -m evaluation detect --detection $(DETECTION) --gate
