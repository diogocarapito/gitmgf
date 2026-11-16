# gitmgf — developer shortcuts (see CLAUDE.md "Commands")
PY ?= python
BABEL_KEYWORDS = -k N_ -k t:2

.PHONY: install dev migrate seed test lint fmt typecheck i18n i18n-check run check docker

install:
	$(PY) -m pip install -r requirements-dev.txt

migrate:
	alembic upgrade head

seed:
	$(PY) -m app.cli seed categories
	$(PY) -m app.cli seed certifications

dev: migrate seed
	uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check . && ruff format --check .

fmt:
	ruff check . --fix && ruff format .

typecheck:
	mypy app/services

# Extract → merge into the EN catalogue → compile. Translate new entries in
# app/locales/en/LC_MESSAGES/messages.po (msgids are the PT-PT strings, D11).
i18n:
	pybabel extract -F babel.cfg $(BABEL_KEYWORDS) --no-location --sort-output -o app/locales/messages.pot .
	pybabel update -i app/locales/messages.pot -d app/locales -D messages --no-fuzzy-matching --ignore-obsolete
	pybabel compile -d app/locales -D messages

i18n-check:
	pytest -q tests/test_i18n.py::test_english_catalogue_is_complete

check: lint typecheck test

docker:
	docker compose up --build
