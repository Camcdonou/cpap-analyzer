.PHONY: help dev up down logs load build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ── Local dev ────────────────────────────────────────────────────────────

dev: ## Run locally (no Docker)
	@echo "Starting backend on :8000..."
	@cd backend && uvicorn app.main:app --port 8000 --reload &
	@echo "Starting frontend on :3000..."
	@cd frontend && npm run dev &
	@echo "Open http://localhost:3000"

# ── Docker ───────────────────────────────────────────────────────────────

build: ## Build Docker images
	docker compose build

up: ## Start all services
	docker compose up -d
	@echo "Open http://localhost:3000"

down: ## Stop all services
	docker compose down

logs: ## Tail logs
	docker compose logs -f

load: ## Load CPAP data into Docker volume (pass SD_CARD_PATH=/path/to/data)
	@echo "Loading data from $(SD_CARD_PATH)..."
	docker compose run --rm backend python load_data.py /data/sd_card
	@echo "Done! Start with: make up"

# ── Data management ─────────────────────────────────────────────────────

shell: ## Open a shell in the backend container
	docker compose exec backend /bin/bash

reset-db: ## Delete the database and start fresh
	docker compose down -v
