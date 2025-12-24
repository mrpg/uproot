.DEFAULT_GOAL := all

.PHONY: help install test lint format type-check security quality all clean requirements

help:
	@echo "Available commands:"
	@echo "  make install        - Install development dependencies"
	@echo "  make requirements   - Compile requirements.txt from pyproject.toml"
	@echo "  make test           - Run tests with coverage"
	@echo "  make lint           - Run linting checks (ruff, black, isort)"
	@echo "  make format         - Auto-format code (black, isort)"
	@echo "  make type-check     - Run mypy type checking"
	@echo "  make security       - Run security scans (bandit, pip-audit, semgrep)"
	@echo "  make quality        - Run code quality checks (radon, deptry)"
	@echo "  make all            - Run all checks (lint, type-check, security, quality, test)"
	@echo "  make pre-commit     - Install and run pre-commit hooks"
	@echo "  make clean          - Remove build artifacts and cache"

install:
	pip install -e ".[dev]"
	pre-commit install

requirements:
	@echo "Compiling requirements.txt from pyproject.toml..."
	pip-compile --resolver=backtracking --output-file=requirements.txt pyproject.toml
	@echo "Compiling requirements-dev.txt from pyproject.toml..."
	pip-compile --resolver=backtracking --extra=dev --output-file=requirements-dev.txt pyproject.toml
	@echo "Requirements compiled successfully!"

test:
	pytest --cov=uproot --cov-report=term-missing --cov-report=html

lint:
	ruff check src/uproot/
	black --check src/uproot/
	isort --check-only src/uproot/

format:
	black src/uproot/
	isort src/uproot/
	ruff check --fix src/uproot/

type-check:
	mypy src/uproot/

security:
	@echo "Running bandit..."
	bandit -r src/uproot/ -c pyproject.toml
	@echo "\nRunning pip-audit..."
	pip-audit
	@echo "\nRunning semgrep..."
	semgrep scan --config=auto src/uproot/ || true

quality:
	@echo "Running deptry..."
	deptry src/uproot/
	@echo "\nRunning radon complexity check..."
	radon cc src/uproot/ -a -nb
	@echo "\nRunning radon maintainability check..."
	radon mi src/uproot/ -nb

pre-commit:
	pre-commit install
	pre-commit run --all-files

all: lint type-check security quality test
	@echo "\n✓ All checks passed!"

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
