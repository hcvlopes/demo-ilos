# Decisoes tecnicas

Log de decisoes de arquitetura e tecnologia.

---

## D001 — Stack principal (F0)

**Data:** 2026-08-01

| Camada | Escolha | Justificativa |
|---|---|---|
| Grafo | FalkorDB (container) | Grafo sobre Redis; openCypher nativo; leve e rapido para demo |
| Backend | Python 3.12 + FastAPI 0.115 + Pydantic 2.11 | Intencao tipada mapeia direto em modelo Pydantic; async nativo |
| Calculo | NumPy 2.2 + SciPy 1.15 | Estimador de lambda e intervalo de confianca |
| Driver grafo | falkordb 1.6 | Driver oficial Python para FalkorDB |
| Testes | pytest 8.3 | Padrao de facto Python |
| LLM | API Anthropic (anthropic 0.52) | So classificacao de intencao — nunca gera Cypher |
| Lint | Ruff 0.11 | Rapido, substitui flake8+isort+black |
| Serializacao fixtures | PyYAML 6.0 | Fixtures ISO 14224 e perfis setoriais em YAML |

## D002 — Estrutura como subdiretorio (F0)

**Data:** 2026-08-01

Demo construida em `demo-ilos/` dentro do repo `asset-inventory-studio` para
manter separacao do produto existente. Pode ser extraida para repo proprio
quando necessario. O schema e o ativo exportavel.

## D003 — Frontend (pendente F7)

Decisao de biblioteca de grafo force-directed adiada para F7. Candidatas:
`react-force-graph`, `@antv/g6`, `cytoscape.js`. Justificativa sera registrada
no PR.

## D004 — Migracao Neo4j → FalkorDB

**Data:** 2026-08-02

Substituicao do backend de grafo de Neo4j 5.26 para FalkorDB.
Adapter `db/adapter.py` encapsula a API FalkorDB para manter compatibilidade
com o padrao session.run()/record["campo"]/dict(node) usado em intents e seeders.
Migrations usam CREATE INDEX em vez de CREATE CONSTRAINT (FalkorDB nao suporta
uniqueness constraints — MERGE garante idempotencia nos seeders).
