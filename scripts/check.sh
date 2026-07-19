#!/usr/bin/env bash
set -e

echo "=== Running Ruff Format Check ==="
ruff format --check src tests

echo "=== Running Ruff Lint Check ==="
ruff check src tests

echo "=== Running pytest ==="
python3 -m pytest
