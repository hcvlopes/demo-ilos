"""Testes do seeder agro — validacao offline (sem FalkorDB).

Verifica que a definição da planta cobre todas as classes taxonômicas,
que os IDs são únicos, que os modos de falha respeitam aplicabilidade,
e que o grafo não contém vocabulário setorial proibido.
"""

import numpy as np
import pytest

from seed.agro.seeder import (
    ALIMENTA,
    ATIVOS,
    CONTRATO,
    DEFEITOS,
    EDIFICACAO,
    ENTREGA,
    EQUIPAMENTOS,
    FUNCOES,
    N_REGISTROS_CONDICAO,
    PONTO_MEDICAO_PROTAGONISTA,
    PROCESSO,
    PROTAGONISTA_ID,
    REDUNDA_COM,
    SISTEMAS,
    _equipamentos_por_classe,
    _modos_para_classe,
)
from seed.generator.fixtures_loader import (
    carregar_classes_taxonomia,
    carregar_lambda_verdadeiro,
    carregar_modos_falha,
)
from seed.generator.poisson import PERFIL_SAFRA_AGRO, gerar_historico

TERMOS_PROIBIDOS = ["safra", "silo", "religamento", "colheita", "plantio"]


class TestDefinicaoPlanta:
    """Validação estática da definição da planta."""

    def test_todas_classes_representadas(self):
        """Todos os 15 tipos taxonômicos têm pelo menos um equipamento."""
        classes_fixture = {c["classe_id"] for c in carregar_classes_taxonomia()}
        classes_planta = {eq["classe"] for eq in EQUIPAMENTOS}
        faltando = classes_fixture - classes_planta
        assert not faltando, f"Classes sem equipamento na planta: {faltando}"

    def test_ids_equipamentos_unicos(self):
        """Nenhum ID de equipamento duplicado."""
        ids = [eq["id"] for eq in EQUIPAMENTOS]
        assert len(ids) == len(set(ids))

    def test_ids_ativos_unicos(self):
        ids = [a["id"] for a in ATIVOS]
        assert len(ids) == len(set(ids))

    def test_ids_sistemas_unicos(self):
        ids = [s["id"] for s in SISTEMAS]
        assert len(ids) == len(set(ids))

    def test_equipamentos_referem_ativos_validos(self):
        """Todo equipamento aponta para um ativo existente."""
        ativos_ids = {a["id"] for a in ATIVOS}
        for eq in EQUIPAMENTOS:
            assert eq["ativo"] in ativos_ids, (
                f"Equipamento {eq['id']} refere ativo inexistente {eq['ativo']}"
            )

    def test_ativos_referem_sistemas_validos(self):
        """Todo ativo aponta para um sistema existente."""
        sistemas_ids = {s["id"] for s in SISTEMAS}
        for atv in ATIVOS:
            assert atv["sistema"] in sistemas_ids, (
                f"Ativo {atv['id']} refere sistema inexistente {atv['sistema']}"
            )

    def test_equipamentos_referem_classes_validas(self):
        """Todo equipamento aponta para uma classe taxonômica das fixtures."""
        classes_fixture = {c["classe_id"] for c in carregar_classes_taxonomia()}
        for eq in EQUIPAMENTOS:
            assert eq["classe"] in classes_fixture, (
                f"Equipamento {eq['id']} refere classe inexistente {eq['classe']}"
            )


class TestVocabularioNeutro:
    """Vocabulário setorial nunca aparece em propriedades de nó (regra 3)."""

    def test_sem_termos_proibidos_edificacao(self):
        for termo in TERMOS_PROIBIDOS:
            assert termo not in EDIFICACAO["descricao"].lower()

    def test_sem_termos_proibidos_sistemas(self):
        for sis in SISTEMAS:
            for termo in TERMOS_PROIBIDOS:
                assert termo not in sis["descricao"].lower(), (
                    f"Termo proibido '{termo}' em sistema {sis['id']}"
                )

    def test_sem_termos_proibidos_ativos(self):
        for atv in ATIVOS:
            for termo in TERMOS_PROIBIDOS:
                assert termo not in atv["descricao"].lower(), (
                    f"Termo proibido '{termo}' em ativo {atv['id']}"
                )

    def test_sem_termos_proibidos_equipamentos(self):
        for eq in EQUIPAMENTOS:
            for termo in TERMOS_PROIBIDOS:
                assert termo not in eq["descricao"].lower(), (
                    f"Termo proibido '{termo}' em equipamento {eq['id']}"
                )


class TestModosAplicaveis:
    """Modos de falha respeitam a matriz de aplicabilidade."""

    def test_toda_classe_tem_modos_aplicaveis(self):
        """Toda classe usada na planta tem pelo menos um modo de falha aplicável."""
        modos = carregar_modos_falha()
        classes_planta = {eq["classe"] for eq in EQUIPAMENTOS}
        sem_modo = []
        for classe_id in classes_planta:
            aplicaveis = _modos_para_classe(modos, classe_id)
            if not aplicaveis:
                sem_modo.append(classe_id)
        assert not sem_modo, f"Classes sem modo de falha aplicável: {sem_modo}"


class TestGeracaoEventos:
    """Verifica que a geração de eventos funciona para toda classe da planta."""

    def test_gera_historico_para_cada_classe(self):
        """Gerar histórico para cada classe não levanta exceção."""
        rng = np.random.default_rng(2)
        lambdas = carregar_lambda_verdadeiro()
        eq_por_classe = _equipamentos_por_classe()

        for classe_id, eqs in eq_por_classe.items():
            lambda_v = lambdas[classe_id]
            for eq in eqs:
                hist = gerar_historico(
                    classe_id=classe_id,
                    lambda_por_hora_op=lambda_v,
                    n_meses=24,
                    perfil=PERFIL_SAFRA_AGRO,
                    rng=rng,
                    n_equipamentos=1,
                )
                assert hist.horas_operacao_total > 0

    def test_numero_total_eventos_razoavel(self):
        """O volume total de eventos é razoável (não vazio, não absurdo)."""
        rng = np.random.default_rng(2)
        lambdas = carregar_lambda_verdadeiro()
        eq_por_classe = _equipamentos_por_classe()
        total = 0

        for classe_id, eqs in eq_por_classe.items():
            lambda_v = lambdas[classe_id]
            for eq in eqs:
                hist = gerar_historico(
                    classe_id=classe_id,
                    lambda_por_hora_op=lambda_v,
                    n_meses=24,
                    perfil=PERFIL_SAFRA_AGRO,
                    rng=rng,
                    n_equipamentos=1,
                )
                total += len(hist.eventos)

        assert 50 < total < 5000, f"Total de eventos ({total}) fora do esperado"


class TestDefeitosEProtagonista:
    """Validação dos defeitos abertos e do protagonista."""

    def test_cinco_defeitos(self):
        assert len(DEFEITOS) == 5

    def test_protagonista_existe(self):
        ids = {d["id"] for d in DEFEITOS}
        assert PROTAGONISTA_ID in ids

    def test_defeitos_referem_equipamentos_validos(self):
        eq_ids = {eq["id"] for eq in EQUIPAMENTOS}
        for d in DEFEITOS:
            assert d["equipamento"] in eq_ids, (
                f"Defeito {d['id']} refere equipamento inexistente {d['equipamento']}"
            )

    def test_modos_defeitos_sao_validos(self):
        modos = carregar_modos_falha()
        modos_ids = {m["codigo"] for m in modos}
        for d in DEFEITOS:
            assert d["modo"] in modos_ids, (
                f"Defeito {d['id']} usa modo inexistente {d['modo']}"
            )


class TestTopologia:
    """Validação de ALIMENTA e REDUNDA_COM."""

    def test_alimenta_refere_ativos_validos(self):
        ativos_ids = {a["id"] for a in ATIVOS}
        for origem, destino in ALIMENTA:
            assert origem in ativos_ids, f"ALIMENTA origem {origem} inexistente"
            assert destino in ativos_ids, f"ALIMENTA destino {destino} inexistente"

    def test_redunda_com_tem_capacidade(self):
        for a1, a2, cap in REDUNDA_COM:
            assert 0.0 < cap <= 1.0, f"Capacidade {cap} fora do intervalo (0, 1]"

    def test_caminho_contrato_ate_ativo(self):
        """Verifica que a cadeia Contrato→Entrega→Processo→Funcao→Ativo é completa."""
        assert CONTRATO["id"]
        assert ENTREGA["id"]
        assert PROCESSO["id"]
        assert len(FUNCOES) > 0
        fun_ativos = {f["ativo"] for f in FUNCOES}
        ativos_ids = {a["id"] for a in ATIVOS}
        assert fun_ativos.issubset(ativos_ids)


class TestMonitoramento:
    """Validação do monitoramento de condição."""

    def test_ponto_medicao_tem_limite_alarme(self):
        assert PONTO_MEDICAO_PROTAGONISTA["limite_alarme"] > 0

    def test_registros_condicao_suficientes(self):
        assert N_REGISTROS_CONDICAO >= 10
