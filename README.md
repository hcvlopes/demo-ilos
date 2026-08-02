# Demo ILOS — Agentes sobre Grafo de Ativos Industriais

Demo de agentes sobre grafo de conhecimento de ativos industriais para o
Congresso ILOS. Dois setores de referência: armazenagem de grãos (agro) e
subestação de distribuidora de energia (elétrico).

## Stack

- **FalkorDB** — banco de grafo sobre Redis (openCypher)
- **FastAPI** — API de intenções tipadas com envelope de evidência
- **Ollama + Llama 3.1** — classificação de intenção via LLM local

## Quickstart

```bash
# 1. Instalar Ollama (https://ollama.com)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Baixar o modelo
ollama pull llama3.1

# 3. Instalar dependências Python
pip install -e .

# 4. Subir FalkorDB
make up

# 5. Semear dados (agro + elétrico)
make seed-agro
make seed-eletrico

# 6. Rodar API + UI
make serve
# Acesse http://localhost:8000

# Rodar testes (190 testes offline)
make test
```

## Estrutura

```
api/           — FastAPI + orquestrador de intenção
db/            — Adapter FalkorDB (compatível com API neo4j-driver)
intents/       — Intenções tipadas (explicar_defeito, historico, risco, ações)
ontology/      — Schema do grafo + migrations idempotentes
scoring/       — Motor de escore de risco (P(falha) × impacto × redundância)
seed/          — Seeders agro e elétrico (Poisson não-homogêneo)
fixtures/      — ISO 14224 (modos, causas, mecanismos, classes taxonômicas)
vocab/         — Perfis setoriais (vocabulário resolvido em render time)
web/           — SPA self-contained (chat + painel de evidência)
tests/         — 190 testes offline
docs/          — Decisões, progresso, ontologia
```

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `FALKORDB_HOST` | `localhost` | Host do FalkorDB/Redis |
| `FALKORDB_PORT` | `6379` | Porta do FalkorDB/Redis |
| `FALKORDB_GRAPH` | `demo_ilos` | Nome do grafo |
| `OLLAMA_HOST` | `http://localhost:11434` | URL do servidor Ollama |
| `OLLAMA_MODEL` | `llama3.1` | Modelo LLM a usar |

## Licença

Proprietário — Datamint
