.PHONY: up down test seed-agro seed-eletrico schema-doc lint serve llm-check

# O projeto exige Python 3.11+ (pyproject: requires-python). O `python3` do
# macOS costuma ser o 3.9 do Command Line Tools, que nao entende `X | None`.
# Procura o primeiro interpretador 3.11+ disponivel; cai para python3 para
# que o guard abaixo produza uma mensagem util em vez de um traceback.
# Sobrescreva com: make test PYTHON=.venv/bin/python
# Ordem importa: o `python3` do PATH (ou do venv ativo) vem primeiro, porque
# e nele que as dependencias normalmente estao instaladas. Versoes explicitas
# so entram se o padrao for velho demais — nao adianta achar um 3.13 limpo.
PYTHON ?= $(shell for p in python3 python python3.13 python3.12 python3.11; do \
		command -v $$p >/dev/null 2>&1 || continue; \
		$$p -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null \
			&& { echo $$p; break; }; \
	done | head -1)
PYTHON := $(if $(strip $(PYTHON)),$(strip $(PYTHON)),python3)

# Falha cedo e legivel: versao do interpretador, depois dependencias.
# Sem isso o usuario recebe um traceback de pydantic ou um ModuleNotFoundError
# cru, que nao dizem qual e a acao corretiva.
define exigir_python
@$(PYTHON) -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null || { \
	echo ""; \
	echo "ERRO: este projeto precisa de Python 3.11+."; \
	echo "  encontrado: $(PYTHON) — $$($(PYTHON) -V 2>&1)"; \
	echo "  (o python3 do macOS e o 3.9 do Command Line Tools)"; \
	echo ""; \
	echo "  macOS (Homebrew):"; \
	echo "    brew install python@3.12"; \
	echo "    python3.12 -m venv .venv"; \
	echo "    .venv/bin/pip install -e ."; \
	echo "    make $@ PYTHON=.venv/bin/python"; \
	echo ""; \
	exit 1; \
}
@$(PYTHON) -c 'import pydantic, falkordb, fastapi' 2>/dev/null || { \
	echo ""; \
	echo "ERRO: dependencias do projeto ausentes em $(PYTHON)."; \
	echo "  versao: $$($(PYTHON) -V 2>&1)"; \
	echo ""; \
	echo "  instale nesse mesmo interpretador:"; \
	echo "    $(PYTHON) -m pip install -e ."; \
	echo ""; \
	echo "  ou use um venv dedicado:"; \
	echo "    $(PYTHON) -m venv .venv && .venv/bin/pip install -e ."; \
	echo "    make $@ PYTHON=.venv/bin/python"; \
	echo ""; \
	exit 1; \
}
endef

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
	$(exigir_python)
	$(PYTHON) -m seed.agro.seeder

seed-eletrico:
	$(exigir_python)
	$(PYTHON) -m seed.eletrico.seeder

test:
	$(exigir_python)
	$(PYTHON) -m pytest tests/ -v

schema-doc:
	$(exigir_python)
	$(PYTHON) -m ontology.export_schema

serve:
	$(exigir_python)
	$(PYTHON) -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

llm-check:
	$(exigir_python)
	@$(PYTHON) -c "from api.orquestrador import verificar_ollama; \
	i = verificar_ollama(); \
	print(('OK  ' if i['disponivel'] else 'FALHA ') + i['detalhe']); \
	print('modelos: ' + (', '.join(i['modelos_disponiveis']) or '(nenhum)')); \
	raise SystemExit(0 if i['disponivel'] else 1)"

lint:
	$(exigir_python)
	$(PYTHON) -m ruff check .
