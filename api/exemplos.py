"""Corpus de exemplos e selecao few-shot.

O corpus inteiro nao cabe no prompt — sao dezenas de consultas, e despejar
todas gastaria contexto que o modelo usaria melhor raciocinando. A selecao
escolhe as mais proximas da pergunta.

A proximidade e por sobreposicao de palavras, nao por embedding. E uma escolha
consciente: embedding exigiria um modelo a mais rodando, e para um corpus
desta ordem a sobreposicao ja separa "quantos defeitos abertos" de "quais
fabricantes". Se o corpus crescer muito, vale reavaliar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Palavras que aparecem em quase toda pergunta e nao ajudam a distinguir.
_VAZIAS = {
    "a", "as", "o", "os", "um", "uma", "de", "do", "da", "dos", "das", "em",
    "no", "na", "nos", "nas", "por", "para", "com", "que", "qual", "quais",
    "quanto", "quantos", "quantas", "e", "ou", "se", "ao", "aos", "sao",
    "esta", "estao", "tem", "existe", "existem", "me", "mostre", "liste",
}


@dataclass(frozen=True)
class ExemploConsulta:
    pergunta: str
    cypher: str
    categoria: str


def _normalizar(texto: str) -> set[str]:
    """Minusculas, sem acento, sem palavra vazia."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    palavras = re.findall(r"[a-z0-9\-]+", sem_acento)
    return {p for p in palavras if p not in _VAZIAS and len(p) > 2}


_cache: list[ExemploConsulta] | None = None


def carregar_exemplos() -> list[ExemploConsulta]:
    """Le o corpus da fixture. Cacheado — o arquivo nao muda em execucao."""
    global _cache
    if _cache is not None:
        return _cache

    caminho = FIXTURES_DIR / "exemplos_consulta.yaml"
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    _cache = [
        ExemploConsulta(
            pergunta=e["pergunta"],
            cypher=e["cypher"].strip(),
            categoria=e.get("categoria", "outros"),
        )
        for e in dados.get("exemplos", [])
    ]
    return _cache


def selecionar(pergunta: str, quantos: int = 6) -> list[ExemploConsulta]:
    """Exemplos mais proximos da pergunta, do mais para o menos relevante.

    Pergunta sem sobreposicao alguma devolve os primeiros do corpus: e melhor
    mostrar o estilo esperado do que nao mostrar nada. O modelo copia forma
    (LIMIT, `AS` em toda coluna) mesmo de exemplo tematicamente distante.
    """
    exemplos = carregar_exemplos()
    if not exemplos:
        return []

    alvo = _normalizar(pergunta)
    if not alvo:
        return exemplos[:quantos]

    pontuados = []
    for ex in exemplos:
        palavras = _normalizar(ex.pergunta)
        comuns = len(alvo & palavras)
        if not comuns:
            continue
        # Normaliza pela uniao para nao favorecer exemplo de pergunta longa.
        score = comuns / len(alvo | palavras)
        pontuados.append((score, ex))

    if not pontuados:
        return exemplos[:quantos]

    pontuados.sort(key=lambda par: par[0], reverse=True)
    return [ex for _score, ex in pontuados[:quantos]]


def formatar_para_prompt(exemplos: list[ExemploConsulta]) -> str:
    """Blocos pergunta/consulta no formato que o modelo deve imitar."""
    if not exemplos:
        return ""
    partes = ["Exemplos de consultas corretas para este schema:", ""]
    for ex in exemplos:
        partes.append(f"Pergunta: {ex.pergunta}")
        partes.append(f"Cypher: {ex.cypher}")
        partes.append("")
    return "\n".join(partes)


def categorias() -> set[str]:
    return {e.categoria for e in carregar_exemplos()}
