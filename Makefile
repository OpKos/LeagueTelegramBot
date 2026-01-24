SHELL := /bin/bash

SRC_DIRS := src app scripts tests

.PHONY: lint format typecheck pre-commit run

lint:
	ruff check $(SRC_DIRS)

format:
	ruff format $(SRC_DIRS)

typecheck:
	mypy

pre-commit:
	pre-commit run -a

run:
	python scripts/run_bot.py
