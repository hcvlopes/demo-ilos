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
# 1. Instalar Ollama — macOS
brew install --cask ollama    # ou baixe o .app em https://ollama.com/download
# Linux:
#   curl -fsSL https://ollama.com/install.sh | sh

# 2. Subir o servidor Ollama
#   macOS: abra o app Ollama (fica na barra de menu) — ele sobe sozinho na 11434
#   Linux: systemctl start ollama   (ou rode `ollama serve` num terminal)

# 3. Baixar o modelo (~4,7 GB no llama3.1:8b)
ollama pull llama3.1

# 4. Instalar dependências Python
pip install -e .

# 5. Conferir que o LLM está de pé antes de subir a demo
make llm-check

# 6. Subir FalkorDB
make up

# 7. Semear dados (agro + elétrico)
make seed-agro
make seed-eletrico

# 8. Rodar API + UI
make serve
# Acesse http://localhost:8000

# Rodar testes (204 testes offline)
make test
```

## Classificador de intenção

A classificação de intenção usa **Ollama local**. Se o Ollama não estiver
acessível, o sistema degrada para um **classificador por regex** em
`api/orquestrador.py` — a demo continua de pé, mas só entende perguntas
próximas dos padrões cadastrados, em vez de linguagem livre.

Essa degradação nunca é silenciosa:

- `GET /saude` devolve `llm.disponivel`, `llm.detalhe` e `classificador`
  (`"llm"` ou `"fallback-regex"`).
- `POST /pergunta` devolve `origem_classificacao` e, quando degradou,
  `motivo_fallback` com a causa.
- A UI mostra um selo verde `LLM: llama3.1` ou âmbar `LLM off - regex` no
  cabeçalho, e marca cada resposta com o classificador que a produziu.

Em qualquer um dos dois caminhos a regra inviolável se mantém: **o LLM nunca
escreve Cypher**. Ele só devolve o nome de uma intenção e parâmetros, que são
validados contra o registry e tipados por Pydantic antes de qualquer
travessia. Parâmetro que não esteja declarado na intenção é descartado, e
intenção inexistente é rejeitada — ambos cobertos em `tests/test_ollama.py`.

### Diagnóstico

```bash
make llm-check          # servidor alcançável + modelo baixado
curl -s localhost:11434/api/tags        # o que o Ollama tem instalado
curl -s localhost:8000/saude | jq .llm  # o que a API está enxergando
```

| Sintoma | Causa provável |
|---|---|
| `Servidor Ollama inacessivel` | App do Ollama fechado, ou `OLLAMA_HOST` errado |
| `modelo 'llama3.1' nao foi baixado` | Falta rodar `ollama pull llama3.1` |
| Selo âmbar mesmo com Ollama no ar | API subiu antes do Ollama — reinicie `make serve` |
| `LLM devolveu JSON invalido` | Modelo pequeno demais; prefira `llama3.1:8b` ou maior |

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
tests/         — 204 testes offline
docs/          — Decisões, progresso, ontologia
```

## Variáveis de ambiente

| Variável | Default | Descrição |
|---|---|---|
| `FALKORDB_HOST` | `localhost` | Host do FalkorDB/Redis |
| `FALKORDB_PORT` | `6379` | Porta do FalkorDB/Redis |
| `FALKORDB_GRAPH` | `demo_ilos` | Nome do grafo |
| `OLLAMA_HOST` | `http://localhost:11434` | URL do servidor Ollama |
| `OLLAMA_MODEL` | `llama3.1` | Modelo LLM a usar (precisa estar baixado) |

## Licença

Proprietário — Datamint
