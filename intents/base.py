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
