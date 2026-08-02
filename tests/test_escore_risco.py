"""Testes do motor de escore de risco e intencao ativos_em_risco_por_processo (F5).

Testes offline — validam calculo puro e estrutura da intencao, sem FalkorDB.
"""

import inspect
import math

import pytest
from pydantic import BaseModel

from intents.base import EnvelopeEvidencia, IntencaoBase
from intents.capacidade.ativos_em_risco import (
    AtivosEmRiscoPorProcesso,
    AtivosEmRiscoParams,
    JANELA_PADRAO_HORAS,
)
from intents.registry import REGISTRY, get_intencao
from scoring.risco import (
    EscoreRisco,
    calcular_escore,
    calcular_impacto,
    probabilidade_falha,
)


class TestProbabilidadeFalha:
    """Testes da funcao P(falha) = 1 - exp(-lambda * t)."""

    def test_lambda_zero_retorna_zero(self):
        assert probabilidade_falha(0.0, 720.0) == 0.0

    def test_janela_zero_retorna_zero(self):
        assert probabilidade_falha(0.001, 0.0) == 0.0

    def test_lambda_negativo_retorna_zero(self):
        assert probabilidade_falha(-0.001, 720.0) == 0.0

    def test_valor_correto(self):
        lam = 0.001
        t = 720.0
        esperado = 1.0 - math.exp(-lam * t)
        assert abs(probabilidade_falha(lam, t) - esperado) < 1e-12

    def test_lambda_alto_converge_para_um(self):
        p = probabilidade_falha(1.0, 1000.0)
        assert p > 0.999

    def test_resultado_entre_zero_e_um(self):
        for lam in [0.0001, 0.001, 0.01, 0.1]:
            for t in [1, 100, 720, 8760]:
                p = probabilidade_falha(lam, t)
                assert 0.0 <= p <= 1.0


class TestImpacto:
    """Testes do fator de impacto baseado em downstream."""

    def test_sem_downstream(self):
        assert calcular_impacto(0) == 1.0

    def test_com_downstream(self):
        assert calcular_impacto(3) == 4.0

    def test_negativo_tratado(self):
        assert calcular_impacto(-1) == 1.0


class TestCalcularEscore:
    """Testes da formula composta de escore."""

    def test_formula_basica(self):
        p = 0.5
        impacto = 3.0
        red = 0.0
        assert abs(calcular_escore(p, impacto, red) - 1.5) < 1e-12

    def test_redundancia_total_zera_escore(self):
        assert calcular_escore(0.8, 5.0, 1.0) == 0.0

    def test_redundancia_parcial(self):
        p = 0.5
        impacto = 4.0
        red = 0.6
        esperado = 0.5 * 4.0 * 0.4
        assert abs(calcular_escore(p, impacto, red) - esperado) < 1e-12

    def test_redundancia_clamped(self):
        assert calcular_escore(0.5, 2.0, 1.5) == 0.0
        assert calcular_escore(0.5, 2.0, -0.5) == calcular_escore(0.5, 2.0, 0.0)


class TestEscoreRiscoDataclass:
    """Valida a estrutura do resultado."""

    def test_campos_obrigatorios(self):
        e = EscoreRisco(
            ativo_id="ATV-001",
            escore=0.5,
            p_falha=0.3,
            impacto=2.0,
            fator_redundancia=0.0,
            lambda_hat=0.001,
            janela_horas=720.0,
            ic_inferior_lambda=0.0005,
            ic_superior_lambda=0.002,
        )
        assert e.ativo_id == "ATV-001"
        assert e.defeitos_abertos == []

    def test_com_defeitos(self):
        e = EscoreRisco(
            ativo_id="ATV-001",
            escore=0.5,
            p_falha=0.3,
            impacto=2.0,
            fator_redundancia=0.0,
            lambda_hat=0.001,
            janela_horas=720.0,
            ic_inferior_lambda=0.0005,
            ic_superior_lambda=0.002,
            defeitos_abertos=["DEF-001", "DEF-002"],
        )
        assert len(e.defeitos_abertos) == 2


class TestIntencaoAtivosEmRisco:
    """Validacao estrutural da intencao ativos_em_risco_por_processo."""

    def test_registrada_no_registry(self):
        assert "ativos_em_risco_por_processo" in REGISTRY

    def test_herda_de_base(self):
        assert issubclass(AtivosEmRiscoPorProcesso, IntencaoBase)

    def test_nome_coincide(self):
        inst = AtivosEmRiscoPorProcesso()
        assert inst.nome == "ativos_em_risco_por_processo"

    def test_descricao_nao_vazia(self):
        inst = AtivosEmRiscoPorProcesso()
        assert inst.descricao

    def test_executar_aceita_pydantic(self):
        sig = inspect.signature(AtivosEmRiscoPorProcesso.executar)
        params = list(sig.parameters.values())
        assert len(params) >= 3
        param_type = params[2].annotation
        assert issubclass(param_type, BaseModel)

    def test_get_intencao(self):
        inst = get_intencao("ativos_em_risco_por_processo")
        assert isinstance(inst, IntencaoBase)

    def test_params_tem_janela_default(self):
        p = AtivosEmRiscoParams(processo_id="PO-001")
        assert p.janela_horas == JANELA_PADRAO_HORAS

    def test_params_janela_customizada(self):
        p = AtivosEmRiscoParams(processo_id="PO-001", janela_horas=168.0)
        assert p.janela_horas == 168.0

    def test_params_rejeita_janela_zero(self):
        with pytest.raises(Exception):
            AtivosEmRiscoParams(processo_id="PO-001", janela_horas=0)

    def test_params_rejeita_janela_negativa(self):
        with pytest.raises(Exception):
            AtivosEmRiscoParams(processo_id="PO-001", janela_horas=-100)


class TestRegistryAtualizado:
    """O registry reflete as 4 intencoes (F4 + F5)."""

    def test_registry_tem_quatro_intencoes(self):
        assert len(REGISTRY) >= 4

    def test_todas_herdam_de_base(self):
        for nome, cls in REGISTRY.items():
            assert issubclass(cls, IntencaoBase), (
                f"Intencao '{nome}' nao herda de IntencaoBase"
            )


class TestConsistenciaComSeeder:
    """Verifica que o seeder fornece os dados necessarios para a intencao."""

    def test_processo_existe(self):
        from seed.agro.seeder import PROCESSO
        assert PROCESSO["id"] == "PO-001"

    def test_funcoes_ligam_a_ativos(self):
        from seed.agro.seeder import ATIVOS, FUNCOES
        ativos_ids = {a["id"] for a in ATIVOS}
        for fun in FUNCOES:
            assert fun["ativo"] in ativos_ids

    def test_defeitos_cobrem_multiplos_ativos(self):
        from seed.agro.seeder import DEFEITOS, EQUIPAMENTOS
        eq_para_ativo = {eq["id"]: eq["ativo"] for eq in EQUIPAMENTOS}
        ativos_com_defeito = {eq_para_ativo[d["equipamento"]] for d in DEFEITOS}
        assert len(ativos_com_defeito) >= 3

    def test_alimenta_forma_cadeia(self):
        from seed.agro.seeder import ALIMENTA
        origens = {a[0] for a in ALIMENTA}
        destinos = {a[1] for a in ALIMENTA}
        assert len(origens) > 1
        assert len(destinos) > 1
