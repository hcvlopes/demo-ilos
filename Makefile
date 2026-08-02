.PHONY: up down test seed-agro seed-eletrico schema-doc lint serve llm-check

# macOS nao tem `python`, so `python3`. Um venv ativo tambem resolve para o
# interpretador certo. Sobrescreva com: make test PYTHON=/caminho/para/python
PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)

FALKORDB_HOST ?= localhost
FALKORDB_PORT ?= 6379
FALKORDB_GRAPH ?= demo_ilos
OLLAMA_HOST ?= http://localhost:11434
OLLAMA_MODEL ?= llama3.1

export FALKORDB_HOST
export FALKORDB_PORT
export FALKORDB_GRAPH
export OLLAMA_HOST
export OLLAMA_MODEL

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
	$(PYTHON) -m seed.agro.seeder

seed-eletrico:
	$(PYTHON) -m seed.eletrico.seeder

test:
	$(PYTHON) -m pytest tests/ -v

schema-doc:
	$(PYTHON) -m ontology.export_schema

serve:
	$(PYTHON) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

llm-check:
	@$(PYTHON) -c "from api.orquestrador import verificar_ollama; \
	i = verificar_ollama(); \
	print(('OK  ' if i['disponivel'] else 'FALHA ') + i['detalhe']); \
	print('modelos: ' + (', '.join(i['modelos_disponiveis']) or '(nenhum)')); \
	raise SystemExit(0 if i['disponivel'] else 1)"

lint:
	$(PYTHON) -m ruff check .
