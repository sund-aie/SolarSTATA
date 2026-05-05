.PHONY: help dev dev-backend dev-frontend install-frontend test test-backend test-frontend build lint clean docker docker-up gen-dataset

help:
	@echo "SolarSTATA v3 dev targets:"
	@echo "  make dev            - run backend (:8000) + frontend (:5173) in parallel"
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
	@echo "  make clean          - remove caches and build artifacts"

# Run both dev servers in parallel. Make's -j 2 starts them concurrently and
# Ctrl+C kills the whole job tree, so backend+frontend always live and die
# together.
dev:
	@$(MAKE) -j 2 dev-backend dev-frontend

dev-backend:
	cd backend && python -m pip install -e ".[dev]" >/dev/null
	cd backend && python -m uvicorn solarstata.main:app --reload --host 127.0.0.1 --port 8000

install-frontend:
	cd frontend && npm install --no-audit --no-fund

dev-frontend: install-frontend
	cd frontend && npm run dev -- --host 127.0.0.1 --port 5173

test: test-backend test-frontend

test-backend:
	cd backend && python -m pip install -e ".[dev]" >/dev/null && python -m pytest -v

test-frontend: install-frontend
	cd frontend && npm test

build: install-frontend
	cd frontend && npm run build

gen-dataset:
	cd backend && python -m solarstata.walkthroughs.datasets.generate

lint:
	cd backend && python -m ruff check src tests && python -m mypy src
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
