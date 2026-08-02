.PHONY: up down test seed-agro seed-eletrico schema-doc lint serve

FALKORDB_HOST ?= localhost
FALKORDB_PORT ?= 6379
FALKORDB_GRAPH ?= demo_ilos

export FALKORDB_HOST
export FALKORDB_PORT
export FALKORDB_GRAPH

up:
	docker compose up -d
	@echo "Waiting for FalkorDB to be ready..."
	@until docker compose exec -T falkordb redis-cli PING 2>/dev/null | grep -q PONG; do \
		sleep 2; \
	done
	@echo "FalkorDB is ready."

down:
	docker compose down

seed-agro:
	python -m seed.agro.seeder

seed-eletrico:
	python -m seed.eletrico.seeder

test:
	python -m pytest tests/ -v

schema-doc:
	python -m ontology.export_schema

serve:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

lint:
	python -m ruff check .
