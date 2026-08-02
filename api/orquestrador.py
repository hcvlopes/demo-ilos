"""Orquestrador de classificacao de intencao via LLM.

Fluxo:
1. Recebe pergunta em linguagem natural.
2. Envia ao LLM com lista de intencoes disponiveis e seus parametros.
3. LLM retorna nome da intencao + parametros tipados (JSON).
4. Orquestrador resolve a intencao no registry e executa com sessao do grafo.
5. Retorna EnvelopeEvidencia.

O LLM nunca escreve Cypher — apenas classifica intencao e preenche parametros.
"""

from __future__ import annotations

import json
import os

import re

from pydantic import BaseModel

from intents.base import EnvelopeEvidencia
from intents.registry import REGISTRY, get_intencao


class ClassificacaoIntencao(BaseModel):
    """Resultado da classificacao do LLM."""

    intencao: str
    parametros: dict


class ResultadoOrquestrador(BaseModel):
    """Resultado completo do orquestrador."""

    pergunta: str
    intencao_classificada: str
    parametros: dict
    envelope: EnvelopeEvidencia


def _construir_prompt_sistema() -> str:
    linhas = [
        "Voce e um classificador de intencoes para um sistema de gestao de ativos industriais.",
        "Dada uma pergunta do usuario, identifique a intencao e extraia os parametros.",
        "",
        "Intencoes disponiveis:",
    ]
    for nome, cls in REGISTRY.items():
        inst = cls()
        import inspect
        sig = inspect.signature(cls.executar)
        params = list(sig.parameters.values())
        if len(params) >= 3:
            param_type = params[2].annotation
            campos = list(param_type.model_fields.keys()) if hasattr(param_type, "model_fields") else []
        else:
            campos = []
        linhas.append(f"- {nome}: {inst.descricao}. Parametros: {campos}")

    linhas.extend([
        "",
        "Responda APENAS com JSON valido no formato:",
        '{"intencao": "<nome>", "parametros": {<chave>: <valor>}}',
        "",
        "Se a pergunta nao corresponder a nenhuma intencao, responda:",
        '{"intencao": "desconhecida", "parametros": {}}',
        "",
        "Nao inclua explicacoes, apenas o JSON.",
    ])
    return "\n".join(linhas)


_REGRAS_FALLBACK = [
    (r"expli(?:que|car)\b.*\bprocesso\b", "explicar_processo", "processo_id"),
    (r"expli(?:que|car)\b.*\bdefeito\b", "explicar_defeito", "defeito_id"),
    (r"equipamentos?\b.*\bativo\b|listar?\b.*\bequipamentos?\b", "listar_equipamentos_ativo", "ativo_id"),
    (r"resumo\b.*\bsistema\b|sistema\b.*\bresumo\b", "resumo_sistema", "sistema_id"),
    (r"resumo\b.*\bedifica|edifica.*\bresumo\b", "resumo_edificacao", "edificacao_id"),
    (r"depend[eê]ncia|upstream|downstream", "dependencias_ativo", "ativo_id"),
    (r"defeitos?\s+(aberto|pendente)|aberto.*defeito|quais\s+defeitos|defeitos\s+est[aã]o", "defeitos_abertos", None),
    (r"ord(?:em|ens)\s+(?:de\s+)?manuten[çc][aã]o", "ordens_manutencao", "equipamento_id"),
    (r"norma|regulament|requisito", "normas_aplicaveis", "equipamento_id"),
    (r"monitor|sensor|medi[çc][aã]o|condi[çc][aã]o", "monitoramento_equipamento", "equipamento_id"),
    (r"cadeia\b.*\bfalha|falha.*\bcadeia|modo.*causa.*mecanismo", "cadeia_falha", "defeito_id"),
    (r"estat[ií]stica|lambda|confiabilidade.*classe|classe.*confiabilidade", "estatisticas_classe", "classe_id"),
    (r"impacto.*parada|parada.*impacto|redundância|redund[aâ]ncia", "impacto_parada", "ativo_id"),
    (r"plano.*manuten|manuten.*plano", "plano_manutencao_ativo", "ativo_id"),
    (r"a[çc][oõ]es?\s+permitid|pode\s+fazer|autoriza", "acoes_permitidas", "equipamento_id"),
    (r"hist[oó]rico|eventos?\s+de\s+falha|timeline", "historico_equipamento", "equipamento_id"),
    (r"risco|ranking|escore", "ativos_em_risco_por_processo", "processo_id"),
]

_ID_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]{1,5}){1,3})\b")


def _classificar_fallback(pergunta: str) -> ClassificacaoIntencao:
    """Classificador por regex — fallback quando LLM nao esta disponivel."""
    texto = pergunta.lower()
    for pattern, intencao, param_key in _REGRAS_FALLBACK:
        if re.search(pattern, texto):
            parametros = {}
            if param_key:
                match = _ID_PATTERN.search(pergunta)
                if match:
                    parametros[param_key] = match.group(1)
                else:
                    parametros[param_key] = ""
            return ClassificacaoIntencao(intencao=intencao, parametros=parametros)
    return ClassificacaoIntencao(intencao="desconhecida", parametros={})


def classificar_intencao(
    pergunta: str,
    client=None,
    modelo: str | None = None,
) -> ClassificacaoIntencao:
    """Classifica a intencao via LLM (Ollama) com fallback regex."""
    if modelo is None:
        modelo = os.environ.get("OLLAMA_MODEL", "llama3.1")

    try:
        from ollama import Client as OllamaClient
        if client is None:
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            client = OllamaClient(host=host)

        response = client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _construir_prompt_sistema()},
                {"role": "user", "content": pergunta},
            ],
            format="json",
        )

        texto = response["message"]["content"].strip()

        if texto.startswith("```"):
            linhas = texto.split("\n")
            texto = "\n".join(linhas[1:-1])

        dados = json.loads(texto)
        return ClassificacaoIntencao(
            intencao=dados.get("intencao", "desconhecida"),
            parametros=dados.get("parametros", {}),
        )
    except Exception:
        return _classificar_fallback(pergunta)


def executar_intencao(
    classificacao: ClassificacaoIntencao,
    session,
) -> EnvelopeEvidencia:
    """Resolve e executa a intencao classificada."""
    inst = get_intencao(classificacao.intencao)

    import inspect
    sig = inspect.signature(type(inst).executar)
    params_list = list(sig.parameters.values())
    param_type = params_list[2].annotation

    params_tipados = param_type(**classificacao.parametros)
    return inst.executar(session, params_tipados)


def orquestrar(
    pergunta: str,
    session,
    client: OllamaClient | None = None,
    modelo: str | None = None,
) -> ResultadoOrquestrador:
    """Pipeline completo: pergunta -> classificacao -> execucao -> envelope."""
    classificacao = classificar_intencao(pergunta, client=client, modelo=modelo)
    envelope = executar_intencao(classificacao, session)
    return ResultadoOrquestrador(
        pergunta=pergunta,
        intencao_classificada=classificacao.intencao,
        parametros=classificacao.parametros,
        envelope=envelope,
    )
