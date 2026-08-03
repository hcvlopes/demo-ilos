"""Consulta livre: o LLM escreve o Cypher quando nenhuma intencao cobre.

Este modulo rompe deliberadamente a regra 1 original do projeto ("o LLM nunca
escreve Cypher"), por decisao do dono do produto, para ampliar o alcance das
perguntas. O que ele NAO faz e romper a seguranca junto. Tres camadas:

1. `session.run_somente_leitura()` usa GRAPH.RO_QUERY. Quem recusa escrita e o
   FalkorDB, nao um regex meu — nao ha como escapar por sintaxe criativa.
2. Guarda sintatica antes de enviar, para dar mensagem util em vez de erro do
   servidor, e para barrar procedimentos administrativos que sao tecnicamente
   leitura (`db.labels`, `dbms.*`).
3. LIMIT imposto no fim da consulta, para uma pergunta ampla nao devolver o
   grafo inteiro.

E o Cypher gerado entra no envelope como evidencia. Numa demo cujo argumento e
rastreabilidade, uma consulta gerada que ninguem ve seria pior do que nao ter
a funcionalidade: o usuario tem que poder ler o que foi executado.
"""

from __future__ import annotations

import json
import os
import re

from api.exemplos import formatar_para_prompt, selecionar
from intents.base import (
    CalculoEvidencia,
    EnvelopeEvidencia,
    NoEvidencia,
)
from ontology.schema import (
    NODE_LABELS,
    RELATIONSHIP_SIGNATURES,
)

LIMITE_PADRAO = 50

# Clausulas que alteram o grafo, ou que expoem o servidor. A trava real e o
# RO_QUERY; esta lista existe para falhar antes, com mensagem legivel.
#
# As palavras usam \b nos dois lados de proposito: `(?<![a-z_])set` casaria
# com uma propriedade chamada `setor`, recusando uma consulta legitima.
_CLAUSULAS_PROIBIDAS = [
    (r"\bcreate\b", "CREATE"),
    (r"\bmerge\b", "MERGE"),
    (r"\bdelete\b", "DELETE"),
    (r"\bdetach\b", "DETACH"),
    (r"\bset\b", "SET"),
    (r"\bremove\b", "REMOVE"),
    (r"\bdrop\b", "DROP"),
    (r"\bforeach\b", "FOREACH"),
    (r"\bload\s+csv\b", "LOAD CSV"),
    (r"\bdbms\.", "dbms.*"),
    (r"\bapoc\.", "apoc.*"),
    (r"\bcall\b", "CALL"),
]

_RE_LIMIT = re.compile(r"\blimit\s+\d+\s*$", re.IGNORECASE)
_RE_COMENTARIO = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)


class ConsultaRecusada(ValueError):
    """A consulta gerada nao passou na guarda — nao chega ao banco."""


def descrever_schema() -> str:
    """Schema em texto para o prompt, gerado da ontologia versionada."""
    linhas = ["Rotulos de no:", "  " + ", ".join(NODE_LABELS), "", "Relacoes validas:"]
    linhas.extend(
        f"  (:{origem})-[:{rel}]->(:{destino})"
        for origem, rel, destino in RELATIONSHIP_SIGNATURES
    )
    linhas.extend([
        "",
        "Convencoes:",
        "  - Todo no tem `id` (string) e quase todo tem `descricao`.",
        "  - Defeito tem `status` ('aberto' ou 'resolvido').",
        "  - NotaManutencao e OrdemManutencao tem `tipo` ('corretiva' ou 'preventiva').",
        "  - MetricaConfiabilidade tem `lambda_hat`, `ic_inferior`, `ic_superior`,",
        "    `n_eventos` e `horas_operacao`. Lambda e por hora de OPERACAO.",
        "  - Requisito tem `criticidade` ('alta', 'media', 'baixa').",
        "  - Norma tem `codigo` (ex.: 'NR-12', 'ISO 14224:2016', 'NBR 5410').",
        "  - AcaoPermitida tem `complexidade`; a aresta PERMITE tem `viabilidade`.",
        "  - A aresta REDUNDA_COM tem `capacidade`.",
    ])
    return "\n".join(linhas)


def _prompt_sistema(pergunta: str = "") -> str:
    """Prompt do gerador, com exemplos escolhidos pela proximidade da pergunta.

    Os exemplos vem de fixtures/exemplos_consulta.yaml, e todos foram
    executados contra o grafo semeado (`make exemplos-validar`). Mostrar ao
    modelo uma consulta que nao roda seria pior do que nao mostrar nenhuma.
    """
    exemplos = formatar_para_prompt(selecionar(pergunta)) if pergunta else ""
    bloco_exemplos = f"\n{exemplos}\n" if exemplos else ""

    return f"""Voce traduz perguntas sobre ativos industriais em consultas Cypher \
de LEITURA sobre um grafo FalkorDB (openCypher).

{descrever_schema()}
{bloco_exemplos}
Regras obrigatorias:
- Somente leitura. Nunca use CREATE, MERGE, DELETE, SET, REMOVE, DROP ou FOREACH.
- Use apenas os rotulos e relacoes listados acima. Nao invente rotulo nem relacao.
- Sempre termine com LIMIT (no maximo {LIMITE_PADRAO}).
- Retorne colunas nomeadas e legiveis, com AS. Prefira devolver `descricao`
  alem de `id`, para a resposta poder citar nomes e nao codigos.
- Se a pergunta nao puder ser respondida com este schema, devolve cypher vazio
  e explique em `motivo`.

Responda APENAS com JSON:
{{"cypher": "<consulta>", "motivo": "<vazio, ou o porque de nao dar>"}}"""


def validar_cypher(travessia: str) -> str:
    """Recusa escrita e impoe LIMIT. Devolve a consulta pronta para executar."""
    if not travessia or not travessia.strip():
        raise ConsultaRecusada("O modelo nao produziu consulta para esta pergunta.")

    # Comentario pode esconder clausula; some antes da inspecao.
    limpa = _RE_COMENTARIO.sub(" ", travessia).strip().rstrip(";")
    minuscula = limpa.lower()

    for padrao, rotulo in _CLAUSULAS_PROIBIDAS:
        if re.search(padrao, minuscula):
            raise ConsultaRecusada(
                f"Consulta recusada: contem '{rotulo}'. "
                f"A consulta livre e somente de leitura e nao chama procedimentos.",
            )

    if not minuscula.lstrip().startswith(("match", "with", "unwind", "return", "optional")):
        raise ConsultaRecusada(
            "Consulta recusada: precisa comecar com MATCH, WITH, UNWIND ou RETURN.",
        )

    if not _RE_LIMIT.search(minuscula):
        limpa = f"{limpa}\nLIMIT {LIMITE_PADRAO}"

    return limpa


def gerar_cypher(pergunta: str, client=None, modelo: str | None = None) -> tuple[str, str]:
    """Pede o Cypher ao LLM. Devolve (cypher_validado, motivo_se_vazio)."""
    if modelo is None:
        modelo = os.environ.get("OLLAMA_MODEL", "llama3.1")
    if client is None:
        from api.orquestrador import criar_cliente_ollama

        client = criar_cliente_ollama()

    # A consulta livre depende do LLM: sem ele nao ha o que gerar. Falha de
    # transporte aqui precisa virar ConsultaRecusada, e nao subir crua — o
    # caminho de intencao continua funcionando sem Ollama (fallback regex), e
    # seria confuso a pergunta fora do catalogo devolver erro de conexao.
    try:
        resposta = client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _prompt_sistema(pergunta)},
                {"role": "user", "content": pergunta},
            ],
            format="json",
        )
        texto = resposta["message"]["content"].strip()
    except Exception as e:
        raise ConsultaRecusada(
            "Nenhuma intencao versionada cobre esta pergunta, e a consulta "
            "livre precisa do LLM, que nao respondeu. Reformule usando um dos "
            f"exemplos, ou verifique o Ollama (make llm-check). Detalhe: {e}",
        ) from e

    if texto.startswith("```"):
        texto = "\n".join(texto.split("\n")[1:-1])

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ConsultaRecusada(
            f"O modelo nao devolveu JSON valido ao gerar a consulta: {e}",
        ) from e
    bruto = (dados.get("cypher") or "").strip()
    motivo = (dados.get("motivo") or "").strip()
    if not bruto:
        return "", motivo or "O modelo nao conseguiu traduzir esta pergunta."
    return validar_cypher(bruto), ""


def _valor_legivel(valor):
    """Nó vira id + descricao; o resto passa como esta."""
    if hasattr(valor, "get") and hasattr(valor, "keys"):
        ident = valor.get("id")
        if ident is not None:
            desc = valor.get("descricao") or valor.get("codigo") or ""
            return f"{ident} ({desc})" if desc else str(ident)
        return dict(valor)
    return valor


def executar_consulta_livre(
    pergunta: str,
    session,
    client=None,
    modelo: str | None = None,
) -> tuple[EnvelopeEvidencia, str]:
    """Gera, valida, executa e embrulha em envelope. Devolve (envelope, cypher)."""
    travessia, motivo = gerar_cypher(pergunta, client=client, modelo=modelo)
    if not travessia:
        raise ConsultaRecusada(motivo)

    resultado = session.run_somente_leitura(travessia)
    registros = list(resultado)

    nos: list[NoEvidencia] = []
    ids_vistos: set[str] = set()
    linhas: list[dict] = []

    for registro in registros:
        linha = {}
        # `.keys()` explicito: RecordWrapper nao implementa __iter__, entao
        # `for chave in registro` cairia no protocolo antigo de indice.
        for chave in registro.keys():  # noqa: SIM118
            valor = registro[chave]
            linha[chave] = _valor_legivel(valor)
            # Nó completo tambem entra no grafo de evidencia.
            if hasattr(valor, "get") and valor.get("id") and valor["id"] not in ids_vistos:
                ids_vistos.add(valor["id"])
                nos.append(NoEvidencia(
                    label=chave,
                    id=str(valor["id"]),
                    propriedades={
                        k: v for k, v in dict(valor).items() if k != "id"
                    },
                ))
        linhas.append(linha)

    calculos = [
        CalculoEvidencia(
            nome="linhas_retornadas", formula="count(resultado da consulta gerada)",
            valor=len(linhas), unidade="linhas",
        ),
    ]

    lacunas = [
        (
            "Resposta obtida por consulta gerada pelo modelo, nao por intencao "
            "versionada. A travessia nao passou por revisao nem por teste — "
            "confira o Cypher exibido antes de usar o numero em decisao."
        ),
    ]
    if len(linhas) >= LIMITE_PADRAO:
        lacunas.append(
            f"Resultado truncado em {LIMITE_PADRAO} linhas; pode haver mais.",
        )
    if not linhas:
        lacunas.append("A consulta executou sem erro, mas nao retornou nenhuma linha.")

    afirmacao = _afirmacao_de(linhas)

    return (
        EnvelopeEvidencia(
            afirmacao=afirmacao,
            nos=nos,
            arestas=[],
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        ),
        travessia,
    )


def _afirmacao_de(linhas: list[dict]) -> str:
    """Afirmacao factual sobre o resultado bruto — o narrador cuida da prosa."""
    if not linhas:
        return "A consulta nao retornou nenhum resultado."
    if len(linhas) == 1 and len(linhas[0]) == 1:
        (valor,) = linhas[0].values()
        return f"Resultado: {valor}."
    colunas = ", ".join(linhas[0].keys())
    amostra = "; ".join(
        ", ".join(f"{k}={v}" for k, v in linha.items()) for linha in linhas[:3]
    )
    return (
        f"A consulta retornou {len(linhas)} linha(s) com as colunas {colunas}. "
        f"Primeiras: {amostra}."
    )
