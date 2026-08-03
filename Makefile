.PHONY: up down test seed-agro seed-eletrico schema-doc lint serve llm-check

# O projeto exige Python 3.11+ (pyproject: requires-python). O `python3` do
# macOS costuma ser o 3.9 do Command Line Tools, que nao entende `X | None`.
# Sobrescreva com: make test PYTHON=/caminho/para/python
#
# Ordem de busca, e o porque de cada posicao:
#   1. ./.venv/bin/python  — o venv do proprio projeto, que e o que o README
#      manda criar. Precisa vir primeiro: e o unico interpretador onde as
#      dependencias com certeza foram instaladas para ESTE projeto.
#   2. $VIRTUAL_ENV        — venv ativo em outro diretorio.
#   3. python3 / python    — o padrao do PATH.
#   4. versoes explicitas  — so se o padrao for velho demais. Um python3.13
#      recem-instalado pelo brew esta limpo, entao vem por ultimo.
# A expansao de VIRTUAL_ENV usa ${VAR:+...}: com a variavel vazia o candidato
# inteiro some. Escrever "$VIRTUAL_ENV/bin/python" direto produziria
# "/bin/python" fora de um venv — que existe em muitos Linux e pode ser
# qualquer coisa.
PYTHON ?= $(shell for p in ./.venv/bin/python "$${VIRTUAL_ENV:+$${VIRTUAL_ENV}/bin/python}" \
			python3 python python3.13 python3.12 python3.11; do \
		[ -n "$$p" ] || continue; \
		command -v "$$p" >/dev/null 2>&1 || continue; \
		"$$p" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null \
			|| continue; \
		echo "$$p"; break; \
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
