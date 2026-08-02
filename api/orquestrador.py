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

import anthropic
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


def classificar_intencao(
    pergunta: str,
    client: anthropic.Anthropic | None = None,
    modelo: str | None = None,
) -> ClassificacaoIntencao:
    """Classifica a intencao via LLM Anthropic."""
    if client is None:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    if modelo is None:
        modelo = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    response = client.messages.create(
        model=modelo,
        max_tokens=256,
        system=_construir_prompt_sistema(),
        messages=[{"role": "user", "content": pergunta}],
    )

    texto = response.content[0].text.strip()

    if texto.startswith("```"):
        linhas = texto.split("\n")
        texto = "\n".join(linhas[1:-1])

    dados = json.loads(texto)
    return ClassificacaoIntencao(
        intencao=dados.get("intencao", "desconhecida"),
        parametros=dados.get("parametros", {}),
    )


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
    client: anthropic.Anthropic | None = None,
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
