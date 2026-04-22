.PHONY: install run migrate seed seed-dev lint format format-check test check

PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
RUFF ?= .venv/bin/ruff

install:
	$(PYTHON) -m pip install -e .[dev]

run:
	$(PYTHON) manage.py runserver

migrate:
	$(PYTHON) manage.py migrate

seed:
	$(PYTHON) manage.py seed_reference_data

seed-dev:
	$(PYTHON) manage.py seed_dev_data

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

format-check:
	$(RUFF) format --check .

test:
	$(PYTEST)

check:
	$(PYTHON) manage.py check
