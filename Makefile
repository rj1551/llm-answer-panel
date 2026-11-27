.PHONY: install up dagster down dbt-debug test test-live lint validate collector-build collector-lint deploy invoke

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

# --- Collector (AWS, us-east-2) ---------------------------------------------------------
# sam build needs a python3.12 with pip on PATH; the venv provides one.
SAM := PATH="$(CURDIR)/$(BIN):$$PATH" sam
# The schedule stays DISABLED unless you pass COLLECTION_ENABLED=true (after session 6),
# and every later deploy must pass it again, or the schedule turns back off.
COLLECTION_ENABLED ?= false
SCHEDULE_END_DATE ?=

collector-build:
	cd collector && $(SAM) build

collector-lint:
	$(BIN)/cfn-lint collector/template.yaml

deploy: collector-lint collector-build
	cd collector && $(ENV) sh -c 'test -n "$$ALERT_EMAIL" || { echo "Add ALERT_EMAIL to .env first"; exit 1; }; $(SAM) deploy --parameter-overrides \
	  R2EndpointUrl="$$R2_ENDPOINT_URL" R2Bucket="$$R2_BUCKET" AlertEmail="$$ALERT_EMAIL" \
	  CollectionEnabled=$(COLLECTION_ENABLED) $(if $(SCHEDULE_END_DATE),ScheduleEndDate=$(SCHEDULE_END_DATE),)'

# One manual run, about 288 paid calls. Synchronous, with CLI retries off: a client-side
# timeout retry would start a second paid run.
invoke:
	AWS_MAX_ATTEMPTS=1 aws lambda invoke --function-name llm-panel-collector --region us-east-2 \
	  --cli-read-timeout 960 --payload '$(or $(PAYLOAD),{})' --cli-binary-format raw-in-base64-out \
	  /dev/stdout
