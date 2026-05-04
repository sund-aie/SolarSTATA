.PHONY: help dev-backend test lint clean docker docker-up gen-dataset

help:
	@echo "SolarSTATA v3 dev targets:"
	@echo "  make dev-backend   - install backend deps and run FastAPI on :8000"
	@echo "  make test          - run backend test suite"
	@echo "  make gen-dataset   - regenerate bundled clinic_patients .csv and .dta"
	@echo "  make lint          - run ruff + mypy (Phase 1.1)"
	@echo "  make docker        - build the container image"
	@echo "  make docker-up     - docker-compose up backend"
	@echo "  make clean         - remove caches and build artifacts"

dev-backend:
	cd backend && pip install -e ".[dev]"
	cd backend && uvicorn solarstata.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd backend && pip install -e ".[dev]" && pytest -v

gen-dataset:
	cd backend && python -m solarstata.walkthroughs.datasets.generate

lint:
	cd backend && ruff check src tests && mypy src

docker:
	docker build -t solarstata:dev .

docker-up:
	docker-compose up backend

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.coverage backend/htmlcov backend/dist backend/build
	rm -rf backend/src/*.egg-info
