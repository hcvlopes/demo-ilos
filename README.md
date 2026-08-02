# Demo ILOS — Agentes sobre Grafo de Ativos Industriais

Demo de agentes sobre grafo de conhecimento de ativos industriais para o
Congresso ILOS. Dois setores de referência: armazenagem de grãos (agro) e
subestação de distribuidora de energia (elétrico).

## Stack

- **FalkorDB** — banco de grafo sobre Redis (openCypher)
- **FastAPI** — API de intenções tipadas com envelope de evidência
- **Anthropic Claude** — classificação de intenção via LLM

## Quickstart

```bash
# Subir FalkorDB
make up

# Semear dados (agro + elétrico)
make seed-agro
make seed-eletrico

# Rodar API + UI
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
| `ANTHROPIC_API_KEY` | — | Chave da API Anthropic (para /pergunta) |

## Licença

Proprietário — Datamint
