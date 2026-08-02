"""Testes de envelope e segurança estrutural (F4).

- Itera o registry e valida que toda intenção retorna envelope completo.
- Teste estrutural: nenhuma função em intents/ aceita string de query.
"""

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import BaseModel

from intents.base import EnvelopeEvidencia, IntencaoBase
from intents.registry import REGISTRY, get_intencao


class TestRegistryEEnvelope:
    """Toda intenção no registry é válida e retorna envelope completo."""

    def test_registry_nao_vazio(self):
        assert len(REGISTRY) >= 3

    def test_todas_intencoes_sao_subclasse_de_base(self):
        for nome, cls in REGISTRY.items():
            assert issubclass(cls, IntencaoBase), (
                f"Intencao '{nome}' ({cls}) nao herda de IntencaoBase"
            )

    def test_todas_intencoes_tem_nome_e_descricao(self):
        for nome, cls in REGISTRY.items():
            inst = cls()
            assert hasattr(inst, "nome") and inst.nome, (
                f"Intencao '{nome}' sem atributo 'nome'"
            )
            assert hasattr(inst, "descricao") and inst.descricao, (
                f"Intencao '{nome}' sem atributo 'descricao'"
            )

    def test_nomes_registry_coincidem_com_atributo(self):
        for nome_reg, cls in REGISTRY.items():
            inst = cls()
            assert inst.nome == nome_reg, (
                f"Nome no registry ('{nome_reg}') difere do atributo ({inst.nome})"
            )

    def test_get_intencao_valida(self):
        for nome in REGISTRY:
            inst = get_intencao(nome)
            assert isinstance(inst, IntencaoBase)

    def test_get_intencao_invalida(self):
        with pytest.raises(KeyError):
            get_intencao("intencao_que_nao_existe")

    def test_executar_aceita_pydantic_model(self):
        """O parâmetro `params` de executar tem anotação Pydantic."""
        for nome, cls in REGISTRY.items():
            sig = inspect.signature(cls.executar)
            params_list = list(sig.parameters.values())
            assert len(params_list) >= 3, (
                f"Intencao '{nome}': executar deve ter (self, session, params)"
            )
            param_type = params_list[2].annotation
            assert param_type is not inspect.Parameter.empty, (
                f"Intencao '{nome}': parametro 'params' sem anotacao de tipo"
            )
            assert issubclass(param_type, BaseModel), (
                f"Intencao '{nome}': parametro 'params' deve ser BaseModel, "
                f"encontrado {param_type}"
            )


class TestEnvelopeCompletude:
    """Validação estática do modelo EnvelopeEvidencia."""

    def test_envelope_tem_seis_campos(self):
        campos = set(EnvelopeEvidencia.model_fields.keys())
        esperados = {"afirmacao", "nos", "arestas", "calculos", "normas", "lacunas"}
        assert campos == esperados, (
            f"Campos do envelope: {campos}, esperados: {esperados}"
        )

    def test_envelope_rejeita_campos_faltando(self):
        with pytest.raises(Exception):
            EnvelopeEvidencia(afirmacao="teste")

    def test_envelope_aceita_completo(self):
        env = EnvelopeEvidencia(
            afirmacao="teste",
            nos=[],
            arestas=[],
            calculos=[],
            normas=[],
            lacunas=[],
        )
        assert env.afirmacao == "teste"


class TestSegurancaEstrutural:
    """Nenhuma função em intents/ aceita string de query como parâmetro.

    Isto é código, não convenção. Inspeciona o AST dos módulos de intenção.
    """

    @staticmethod
    def _intents_dir() -> Path:
        return Path(__file__).resolve().parent.parent / "intents"

    def _collect_python_files(self) -> list[Path]:
        return list(self._intents_dir().rglob("*.py"))

    def test_nenhuma_funcao_aceita_query_como_parametro(self):
        """Nenhum parâmetro de função se chama 'query', 'cypher' ou 'consulta'."""
        proibidos = {"query", "cypher", "consulta", "cypher_query", "raw_query"}
        violacoes = []

        for pyfile in self._collect_python_files():
            tree = ast.parse(pyfile.read_text(encoding="utf-8"), filename=str(pyfile))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in node.args.args + node.args.kwonlyargs:
                        if arg.arg in proibidos:
                            violacoes.append(
                                f"{pyfile.name}:{node.name}() tem parametro '{arg.arg}'"
                            )

        assert not violacoes, (
            "Funcoes em intents/ com parametro de query proibido:\n"
            + "\n".join(violacoes)
        )

    def test_nenhum_parametro_str_livre_em_executar(self):
        """O método executar() não aceita str diretamente — apenas Pydantic models."""
        violacoes = []
        for nome, cls in REGISTRY.items():
            sig = inspect.signature(cls.executar)
            for pname, param in sig.parameters.items():
                if pname in ("self", "session"):
                    continue
                ann = param.annotation
                if ann is str:
                    violacoes.append(
                        f"Intencao '{nome}': executar() aceita str em '{pname}'"
                    )

        assert not violacoes, (
            "Intencoes com parametro str em executar() (devem usar BaseModel):\n"
            + "\n".join(violacoes)
        )
