"""Contrato base de intenção e envelope de evidência.

Toda intenção é uma função tipada:
- entrada: modelo Pydantic com parâmetros do usuário (nunca string de query)
- saída: EnvelopeEvidencia com os seis campos obrigatórios

O LLM classifica a intenção e preenche os parâmetros; a travessia do grafo
é código versionado aqui em intents/, nunca Cypher gerado pelo modelo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class NoEvidencia(BaseModel):
    """Nó do grafo retornado como evidência."""

    label: str
    id: str
    propriedades: dict[str, Any] = Field(default_factory=dict)


class ArestaEvidencia(BaseModel):
    """Aresta do grafo retornada como evidência."""

    tipo: str
    origem_id: str
    destino_id: str
    propriedades: dict[str, Any] = Field(default_factory=dict)


class CalculoEvidencia(BaseModel):
    """Cálculo realizado como parte da evidência."""

    nome: str
    formula: str
    valor: float | None = None
    unidade: str = ""
    ic_inferior: float | None = None
    ic_superior: float | None = None


class NormaEvidencia(BaseModel):
    """Norma aplicável citada na evidência."""

    codigo: str
    descricao: str = ""


class EnvelopeEvidencia(BaseModel):
    """Envelope de evidência completo — os seis campos são obrigatórios."""

    afirmacao: str
    nos: list[NoEvidencia]
    arestas: list[ArestaEvidencia]
    calculos: list[CalculoEvidencia]
    normas: list[NormaEvidencia]
    lacunas: list[str]


def contar(session, travessia: str, parameters: dict | None = None, campo: str = "c") -> int:
    """Le um COUNT devolvendo 0 quando nao ha linha.

    `session.run(...).single()[campo]` estoura com TypeError se o resultado
    vier vazio. Contra o banco isso nao acontece — COUNT sempre devolve uma
    linha —, mas o erro resultante e mudo e aparece longe da causa. Aqui a
    ausencia vira zero, que e a resposta certa para uma contagem sem
    resultado.

    O parametro se chama `travessia`, e nao `query`, de proposito: nomes de
    query sao proibidos em intents/ por teste estrutural, justamente para que
    nao exista slot onde uma consulta possa entrar de fora. Este helper e
    plumbing interno e so aceita literal escrito no proprio modulo de
    intencao — ha teste que verifica isso no AST.
    """
    registro = session.run(travessia, parameters=parameters or {}).single()
    if registro is None:
        return 0
    valor = registro[campo]
    return int(valor) if valor is not None else 0


def resolver_no(session, label: str, valor: str, campo_nome: str = "descricao"):
    """Resolve um no por id ou nome, tolerando referencia ausente.

    Perguntas naturais nem sempre carregam o id: "quantos equipamentos o
    centro de trabalho atende" e legitima, mas o classificador nao tem o que
    extrair. Antes isso virava `KeyError: "Centro de trabalho '' nao
    encontrado"` — um 404 que nao diz ao usuario o que fazer.

    Aqui, referencia vazia com um unico no daquele rotulo resolve para ele,
    que e a leitura obvia. Com varios, o erro lista as opcoes em vez de so
    negar.
    """
    if valor:
        registro = session.run(
            f"MATCH (x:{label}) WHERE x.id = $v OR x.{campo_nome} = $v RETURN x",
            parameters={"v": valor},
        ).single()
        if registro is None:
            raise KeyError(f"{label} '{valor}' nao encontrado.")
        return registro["x"]

    candidatos = [r["x"] for r in session.run(f"MATCH (x:{label}) RETURN x ORDER BY x.id")]
    if len(candidatos) == 1:
        return candidatos[0]
    if not candidatos:
        raise KeyError(f"Nenhum {label} cadastrado.")
    opcoes = ", ".join(
        f"{c['id']} ({c.get(campo_nome, '')})" for c in candidatos
    )
    raise KeyError(
        f"Ha {len(candidatos)} {label} — informe qual. Opcoes: {opcoes}",
    )


class IntencaoBase(ABC):
    """Contrato base para todas as intencoes.

    Subclasses implementam `executar` com a travessia do grafo versionada.
    O parametro `session` e uma sessao ativa do banco de grafo.
    """

    nome: str
    descricao: str

    @abstractmethod
    def executar(self, session, params: BaseModel) -> EnvelopeEvidencia:
        ...
