"""Testes do catalogo de acao permitida e papel autorizador (F8).

Testes offline — validam fixtures, schema, seeder e intencao.
"""

import pytest

from intents.base import EnvelopeEvidencia, IntencaoBase
from intents.registry import REGISTRY
from intents.transversais.acoes_permitidas import AcoesPermitidas, AcoesPermitidasParams
from ontology.schema import (
    NODE_LABELS,
    RELATIONSHIP_PROPERTIES,
    RELATIONSHIP_SIGNATURES,
    RELATIONSHIP_TYPES,
)
from seed.agro.seeder import (
    AUTORIZACAO_POR_COMPLEXIDADE,
    DEFEITOS,
    PAPEIS,
    VIABILIDADE_POR_COMPLEXIDADE,
)
from seed.generator.fixtures_loader import carregar_acoes_permitidas, carregar_modos_falha


class TestSchemaF8:
    """O schema inclui AcaoPermitida, Papel e suas relacoes."""

    def test_acao_permitida_no_schema(self):
        assert "AcaoPermitida" in NODE_LABELS

    def test_papel_no_schema(self):
        assert "Papel" in NODE_LABELS

    def test_permite_no_schema(self):
        assert "PERMITE" in RELATIONSHIP_TYPES

    def test_autoriza_no_schema(self):
        assert "AUTORIZA" in RELATIONSHIP_TYPES

    def test_aplicavel_modo_no_schema(self):
        assert "APLICAVEL_MODO" in RELATIONSHIP_TYPES

    def test_assinatura_permite(self):
        assert ("ClasseTaxonomia", "PERMITE", "AcaoPermitida") in RELATIONSHIP_SIGNATURES

    def test_assinatura_autoriza(self):
        assert ("Papel", "AUTORIZA", "AcaoPermitida") in RELATIONSHIP_SIGNATURES

    def test_assinatura_aplicavel_modo(self):
        assert ("AcaoPermitida", "APLICAVEL_MODO", "ModoFalha") in RELATIONSHIP_SIGNATURES

    def test_propriedade_viabilidade(self):
        assert "viabilidade" in RELATIONSHIP_PROPERTIES.get("PERMITE", [])


class TestFixturesAcoesPermitidas:
    """Validacao das fixtures de acoes permitidas."""

    def test_carrega_acoes(self):
        acoes = carregar_acoes_permitidas()
        assert len(acoes) >= 5

    def test_campos_obrigatorios(self):
        acoes = carregar_acoes_permitidas()
        for acao in acoes:
            assert "codigo" in acao
            assert "descricao" in acao
            assert "tipo" in acao
            assert "modos_aplicaveis" in acao
            assert "complexidade" in acao

    def test_codigos_unicos(self):
        acoes = carregar_acoes_permitidas()
        codigos = [a["codigo"] for a in acoes]
        assert len(codigos) == len(set(codigos))

    def test_tipos_validos(self):
        acoes = carregar_acoes_permitidas()
        tipos_validos = {"corretiva", "preventiva", "preditiva"}
        for acao in acoes:
            assert acao["tipo"] in tipos_validos, (
                f"Acao {acao['codigo']} tem tipo invalido: {acao['tipo']}"
            )

    def test_complexidades_validas(self):
        acoes = carregar_acoes_permitidas()
        for acao in acoes:
            assert acao["complexidade"] in VIABILIDADE_POR_COMPLEXIDADE, (
                f"Acao {acao['codigo']} tem complexidade invalida: {acao['complexidade']}"
            )

    def test_modos_aplicaveis_sao_validos(self):
        acoes = carregar_acoes_permitidas()
        modos = carregar_modos_falha()
        modos_ids = {m["codigo"] for m in modos}
        for acao in acoes:
            for modo_id in acao["modos_aplicaveis"]:
                assert modo_id in modos_ids, (
                    f"Acao {acao['codigo']} refere modo inexistente {modo_id}"
                )


class TestPapeisSeeder:
    """Validacao dos papeis autorizadores."""

    def test_tres_papeis(self):
        assert len(PAPEIS) == 3

    def test_papeis_ids_unicos(self):
        ids = [p["id"] for p in PAPEIS]
        assert len(ids) == len(set(ids))

    def test_autorizacao_hierarquica(self):
        """Papeis de nivel mais alto autorizam mais acoes."""
        baixa = set(AUTORIZACAO_POR_COMPLEXIDADE["baixa"])
        media = set(AUTORIZACAO_POR_COMPLEXIDADE["media"])
        alta = set(AUTORIZACAO_POR_COMPLEXIDADE["alta"])
        assert alta.issubset(media)
        assert media.issubset(baixa)


class TestViabilidade:
    """Viabilidade decrescente com complexidade."""

    def test_viabilidade_decrescente(self):
        assert VIABILIDADE_POR_COMPLEXIDADE["baixa"] > VIABILIDADE_POR_COMPLEXIDADE["media"]
        assert VIABILIDADE_POR_COMPLEXIDADE["media"] > VIABILIDADE_POR_COMPLEXIDADE["alta"]

    def test_viabilidade_entre_zero_e_um(self):
        for comp, viab in VIABILIDADE_POR_COMPLEXIDADE.items():
            assert 0.0 < viab <= 1.0, f"Viabilidade {viab} fora do intervalo para {comp}"


class TestIntencaoAcoesPermitidas:
    """Validacao da intencao atualizada (F8)."""

    def test_ainda_no_registry(self):
        assert "acoes_permitidas" in REGISTRY

    def test_descricao_atualizada(self):
        inst = AcoesPermitidas()
        assert "viabilidade" in inst.descricao.lower() or "permitida" in inst.descricao.lower()

    def test_lacunas_f8_removidas(self):
        """A intencao nao deve mais declarar lacunas F8 no codigo."""
        import inspect
        source = inspect.getsource(AcoesPermitidas.executar)
        assert "sem catalogo AcaoPermitida (F8)" not in source
        assert "Sem ordenacao por viabilidade (F8)" not in source
        assert "Sem papel autorizador (F8)" not in source

    def test_defeitos_referem_modos_do_catalogo(self):
        """Os defeitos do seeder usam modos que existem no catalogo."""
        acoes = carregar_acoes_permitidas()
        modos_no_catalogo = set()
        for acao in acoes:
            modos_no_catalogo.update(acao["modos_aplicaveis"])
        for d in DEFEITOS:
            assert d["modo"] in modos_no_catalogo, (
                f"Defeito {d['id']} usa modo {d['modo']} que nao tem acao no catalogo"
            )
