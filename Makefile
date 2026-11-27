.PHONY: install up dagster down dbt-debug test test-live lint validate

VENV := .venv
BIN := $(VENV)/bin
# dotenv loads .env into the environment of each command. Absolute paths, because the
# dbt targets cd into dbt/ first; skipped when there is no .env (e.g. CI).
ENV := $(if $(wildcard .env),$(CURDIR)/$(BIN)/dotenv -f $(CURDIR)/.env run --no-override --,)
DBT := cd dbt && $(ENV) $(CURDIR)/$(BIN)/dbt
export DAGSTER_HOME := $(CURDIR)/.dagster_home

install:
	python3 -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e ".[dev]"

# One command: start ClickHouse, wait until it is healthy, then run Dagster (UI on :3000).
up:
	docker compose up -d --wait
	$(MAKE) dagster

dagster:
	mkdir -p $(DAGSTER_HOME)
	$(ENV) $(BIN)/dagster dev -m orchestration.definitions

down:
	docker compose down

dbt-debug:
	$(DBT) debug --profiles-dir .

test:
	$(BIN)/pytest -q

test-live:
	CLICKHOUSE_LIVE=1 $(ENV) $(BIN)/pytest -q

lint:
	$(BIN)/ruff check .

# Offline checks that need neither Docker nor a database.
validate:
	docker compose config --quiet
	$(ENV) $(BIN)/dagster definitions validate -m orchestration.definitions
	$(DBT) parse --profiles-dir .
