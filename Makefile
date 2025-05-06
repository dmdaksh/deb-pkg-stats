# Makefile

# Define python interpreter
PYTHON = python3

# Define source files
SOURCES = src/package_statistics.py tests/test_package_statistics.py

# Phony targets (targets that don't represent files)
.PHONY: install format lint typecheck test check all clean help

# Default target
all: format check

# Install development dependencies
install:
	$(PYTHON) -m pip install -r requirements-dev.txt

# Format code using black and ruff --fix (for import sorting etc.)
format:
	$(PYTHON) -m black $(SOURCES)
	$(PYTHON) -m ruff check --fix src tests

# Lint code using ruff
lint:
	PYTHONPATH=src $(PYTHON) -m ruff check src tests

# Type check code using mypy
typecheck:
	PYTHONPATH=src $(PYTHON) -m mypy src tests

# Run tests using pytest (configuration is in pyproject.toml)
test:
	PYTHONPATH=src $(PYTHON) -m pytest tests

# Run all checks (lint, typecheck, test)
check: lint typecheck test

# Clean up generated files
clean:
	# Remove root-level caches and coverage artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov
	# Remove LaTeX aux files from the report directory
	rm -f report/*.aux report/*.log report/*.out report/*.fdb_latexmk report/*.fls report/*.synctex.gz report/*_vimtex_selected.log
	# More robustly find and remove pyc/pyo files and __pycache__ dirs recursively
	find . -type f -name '*.py[co]' -delete -o -type d -name '__pycache__' -exec rm -rf {} +

# Help target
help:
	@echo "Makefile targets:"
	@echo "  install    - Install development dependencies from requirements-dev.txt"
	@echo "  format     - Format code using black and ruff --fix"
	@echo "  lint       - Lint code using ruff check"
	@echo "  typecheck  - Type check code using mypy"
	@echo "  test       - Run tests using pytest"
	@echo "  check      - Run lint, typecheck, and test"
	@echo "  all        - Run format and check (default)"
	@echo "  clean      - Remove generated files (__pycache__, .coverage, LaTeX aux files, etc.)"