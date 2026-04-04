.PHONY: install dev test clean docker-init docker-start check

# Python
PY := python3
UV := uv

# Directories
BACKEND_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
ROOT_DIR := $(BACKEND_DIR)/..
HARNESS_DIR := $(BACKEND_DIR)/packages/harness

# Python venv
PYTHON := $(BACKEND_DIR)/.venv/bin/python
PIP := $(BACKEND_DIR)/.venv/bin/pip

# Config
CONFIG := $(BACKEND_DIR)/config.yaml
ENV := $(BACKEND_DIR)/.env

# Default target
all: install dev

# Check environment
check:
	@echo "Checking Python version..."
	@$(PY) --version
	@echo "Checking uv..."
	@which uv || echo "uv not found"
	@echo "Checking config..."
	@test -f $(CONFIG) || (echo "Missing config.yaml" && exit 1)

# Install dependencies
install:
	@echo "Installing dependencies..."
	cd $(BACKEND_DIR) && uv sync

# Development
dev: install
	@echo "Starting FastAPI gateway on port 8000..."
	cd $(BACKEND_DIR) && $(PY) -m uvicorn app.gateway.app:app --host 0.0.0.0 --port 8000 --reload

# Test
test:
	cd $(BACKEND_DIR) && $(PY) -m pytest tests/ -v

# Clean
clean:
	rm -rf $(BACKEND_DIR)/.venv
	rm -rf $(BACKEND_DIR)/.deer-flow
	rm -rf $(BACKEND_DIR)/__pycache__
	find $(HARNESS_DIR) -type d -name __pycache__ -exec rm -rf {} +
	find $(HARNESS_DIR) -type f -name "*.pyc" -delete
