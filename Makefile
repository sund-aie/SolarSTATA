.PHONY: help setup dev dev-backend dev-frontend test test-backend test-frontend build lint clean docker docker-up gen-dataset

# --- Toolchain detection ---------------------------------------------------
# Default to python3 (POSIX-portable; macOS ships it but no `python`). Override
# with `make PYTHON=python3.12 setup` if needed.
PYTHON ?= python3

VENV         := .venv
PY           := $(VENV)/bin/python
NODE_MODULES := frontend/node_modules

# Stamp file marks "deps installed" so `make setup` is idempotent and downstream
# targets only re-trigger when pyproject.toml changes.
SETUP_STAMP  := $(VENV)/.setup-stamp

help:
	@echo "SolarSTATA v3 dev targets:"
	@echo "  make setup          - create .venv (Python) + frontend node_modules"
	@echo "  make dev            - setup, then run backend (:8000) + frontend (:5173) in parallel"
	@echo "  make dev-backend    - run FastAPI on :8000 with auto-reload"
	@echo "  make dev-frontend   - run Vite dev server on :5173"
	@echo "  make test           - run backend + frontend test suites"
	@echo "  make test-backend   - run backend pytest suite"
	@echo "  make test-frontend  - run frontend vitest suite"
	@echo "  make build          - build the frontend for production"
	@echo "  make gen-dataset    - regenerate bundled clinic_patients .csv and .dta"
	@echo "  make lint           - typecheck (tsc) + ruff + mypy"
	@echo "  make docker         - build the container image"
	@echo "  make docker-up      - docker-compose up backend"
	@echo "  make clean          - remove caches, build artifacts, and .venv"

# --- Bootstrap: venv + frontend deps ---------------------------------------
setup: $(SETUP_STAMP) $(NODE_MODULES)

$(SETUP_STAMP): backend/pyproject.toml
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo "ERROR: '$(PYTHON)' not found on PATH. Install Python 3.11+ (https://www.python.org/downloads) or override with 'make PYTHON=python3.12 setup'." >&2; \
		exit 1; \
	}
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating $(VENV) using $(PYTHON)…"; \
		$(PYTHON) -m venv $(VENV); \
	fi
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e backend[dev]
	@touch $(SETUP_STAMP)

$(NODE_MODULES): frontend/package.json
	@command -v npm >/dev/null 2>&1 || { \
		echo "ERROR: 'npm' not found on PATH. Install Node 18+ (https://nodejs.org/)." >&2; \
		exit 1; \
	}
	cd frontend && npm install --no-audit --no-fund
	@touch $(NODE_MODULES)

# --- Dev servers -----------------------------------------------------------
# `-j 2` runs both children concurrently. Ctrl+C kills the whole job tree so
# backend+frontend always live and die together.
dev: setup
	@$(MAKE) -j 2 dev-backend dev-frontend

dev-backend: $(SETUP_STAMP)
	$(PY) -m uvicorn solarstata.main:app --reload --reload-dir backend/src --host 127.0.0.1 --port 8000

dev-frontend: $(NODE_MODULES)
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

# --- Tests -----------------------------------------------------------------
test: test-backend test-frontend

test-backend: $(SETUP_STAMP)
	cd backend && $(CURDIR)/$(PY) -m pytest -v

test-frontend: $(NODE_MODULES)
	cd frontend && npm test

# --- Build / lint / utilities ----------------------------------------------
build: $(NODE_MODULES)
	cd frontend && npm run build

gen-dataset: $(SETUP_STAMP)
	$(PY) -m solarstata.walkthroughs.datasets.generate

lint: $(SETUP_STAMP) $(NODE_MODULES)
	cd backend && $(CURDIR)/$(PY) -m ruff check src tests
	cd backend && $(CURDIR)/$(PY) -m mypy src
	cd frontend && npx tsc --noEmit

docker:
	docker build -t solarstata:dev .

docker-up:
	docker-compose up backend

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.coverage backend/htmlcov backend/dist backend/build
	rm -rf backend/src/*.egg-info
	rm -rf frontend/dist frontend/.vite
	rm -rf $(VENV)
