SHELL := /bin/bash
ENVFILE := deploy/compose/.env
-include $(ENVFILE)
export AIRFLOW_UID := $(shell id -u)
PIPELINE ?= documents
EMBEDDER ?= fake
UNTIL ?= ch20
DAY ?= 0
CHANGES ?= update:5,soft:2,hard:1
export UNTIL
COMPOSE_CORE := docker compose -p llmdata -f deploy/compose/core.yml \
	--env-file deploy/compose/images.env --env-file $(ENVFILE)
SPARK := $(if $(filter spark,$(PROFILE)),-f deploy/compose/spark.yml)
COMPOSE := $(COMPOSE_CORE) $(SPARK)
UV := uv run --frozen
export PGHOST ?= localhost
export PGPORT ?= 55432
export PGUSER ?= llmdata
export PGPASSWORD ?= $(POSTGRES_PASSWORD)

.PHONY: up down clean-all reset data run run-local lint types test \
	verify index-hash watermark trace reembed spike psql

$(ENVFILE):
	@umask 077; { \
	  echo "POSTGRES_PASSWORD=$$(openssl rand -hex 16)"; \
	  echo "AIRFLOW_JWT_SECRET=$$(openssl rand -hex 32)"; \
	  echo "AIRFLOW_SECRET_KEY=$$(openssl rand -hex 32)"; \
	} > $@

up: $(ENVFILE)
	$(COMPOSE) up -d --build --wait postgres
	$(UV) python -m llmdata.db migrate
	$(if $(SPARK),$(COMPOSE_CORE) build airflow)
	$(COMPOSE) up -d --build airflow
	$(UV) python tools/airflow_wait.py

down:
	$(COMPOSE) down

clean-all:
	$(COMPOSE) down -v --rmi local --remove-orphans

data:
	$(UV) python -m llmdata.synthetic --day $(DAY) --changes $(CHANGES)

reset:
	$(UV) python -m llmdata.db reset
	rm -rf data/archive
	$(MAKE) data DAY=0

run:
	$(UV) python tools/airflow_run.py $(PIPELINE) \
	  --conf '{"embedder": "$(EMBEDDER)"}'

run-local:
	$(UV) python -m llmdata.pipeline run $(PIPELINE) --until $(UNTIL) \
	  $(if $(RUN_ID),--run-id $(RUN_ID))

lint:
	$(UV) ruff check .
	$(UV) ruff format --check .

types:
	$(UV) mypy

test:
	$(UV) pytest -q

verify: lint types test

verify-%:
	$(UV) pytest -q --until $*

psql:
	$(COMPOSE) exec postgres psql -U llmdata -d $(or $(DB),llmdata)

index-hash:
	@$(UV) python -m llmdata.index hash

reembed:
	$(COMPOSE) exec airflow /opt/venv/bin/python -m llmdata.embed \
	  reembed $(EMBEDDER)

trace:
	@$(UV) python -m llmdata.identity trace $(CHUNK)

watermark:
	@$(UV) python -m llmdata.freshness show

spike:
	$(UV) python tools/spike/run_spike.py
