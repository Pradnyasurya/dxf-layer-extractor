.PHONY: help install test lint format clean run docker-build docker-run

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	pip install -r requirements.txt

test: ## Run test suite
	pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	pytest tests/ -v --tb=short --cov=. --cov-report=term --cov-report=html

lint: ## Run flake8 linting
	flake8 app.py comparison_engine.py --max-line-length=120 --ignore=E203,W503 --count

format-check: ## Check code formatting with black
	black --check app.py comparison_engine.py

format: ## Format code with black
	black app.py comparison_engine.py

typecheck: ## Run mypy type checking
	mypy app.py comparison_engine.py --ignore-missing-imports

clean: ## Clean up temporary files
	rm -rf __pycache__ .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

run: ## Run the Flask app locally
	python app.py

docker-build: ## Build Docker image
	docker build -t dxf-layer-validator .

docker-run: ## Run Docker container
	docker run -p 8080:8080 dxf-layer-validator

dev-setup: ## Set up development environment
	cp .env.example .env
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	@echo "Development environment ready! Run 'make run' to start."

all-checks: test lint format-check ## Run all checks (tests, lint, format)
