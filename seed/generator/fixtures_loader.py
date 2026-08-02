"""Carrega fixtures de calibração a partir dos YAML."""

from pathlib import Path

import yaml


FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"


def carregar_lambda_verdadeiro() -> dict[str, float]:
    """Retorna {classe_id: lambda_por_hora_operacao}."""
    path = FIXTURES_DIR / "calibracao" / "lambda_verdadeiro.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        c["classe_id"]: c["lambda_por_hora_operacao"]
        for c in data["classes"]
    }


def carregar_classes_taxonomia() -> list[dict]:
    """Retorna lista de classes taxonômicas."""
    path = FIXTURES_DIR / "iso14224" / "classes_taxonomia.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["classes"]


def carregar_modos_falha() -> list[dict]:
    """Retorna lista de modos de falha."""
    path = FIXTURES_DIR / "iso14224" / "modos_falha.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["modos"]


def carregar_causas_falha() -> list[dict]:
    """Retorna lista de causas de falha."""
    path = FIXTURES_DIR / "iso14224" / "causas_falha.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["causas"]


def carregar_mecanismos_falha() -> list[dict]:
    """Retorna lista de mecanismos de falha."""
    path = FIXTURES_DIR / "iso14224" / "mecanismos_falha.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["mecanismos"]


def carregar_acoes_permitidas() -> list[dict]:
    """Retorna lista de ações permitidas."""
    path = FIXTURES_DIR / "iso14224" / "acoes_permitidas.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data
