"""Testes do seeder eletrico — validacao offline (sem FalkorDB).

Verifica que a definicao da subestacao cobre classes taxonomicas,
que os IDs sao unicos, que os modos/causas/mecanismos respeitam fixtures,
e que o grafo nao contem vocabulario setorial proibido.
"""

import numpy as np
import pytest

from seed.eletrico.seeder import (
    ALIMENTA,
    ATIVOS,
    AUTORIZACAO_POR_COMPLEXIDADE,
    CONTRATO,
    DEFEITOS,
    EDIFICACAO,
    ENTREGA,
    EQUIPAMENTOS,
    FUNCOES,
    PAPEIS,
    PROCESSO,
    REDUNDA_COM,
    SISTEMAS,
    VIABILIDADE_POR_COMPLEXIDADE,
    _equipamentos_por_classe,
    _modos_para_classe,
)
from seed.generator.fixtures_loader import (
    carregar_causas_falha,
    carregar_classes_taxonomia,
    carregar_lambda_verdadeiro,
    carregar_mecanismos_falha,
    carregar_modos_falha,
)
from seed.generator.poisson import PERFIL_UNIFORME, gerar_historico

TERMOS_PROIBIDOS = ["safra", "silo", "religamento", "colheita", "plantio"]


class TestDefinicaoPlanta:
    """Validacao estatica da definicao da subestacao."""

    def test_ids_equipamentos_unicos(self):
        ids = [eq["id"] for eq in EQUIPAMENTOS]
        assert len(ids) == len(set(ids))

    def test_ids_ativos_unicos(self):
        ids = [a["id"] for a in ATIVOS]
        assert len(ids) == len(set(ids))

    def test_ids_sistemas_unicos(self):
        ids = [s["id"] for s in SISTEMAS]
        assert len(ids) == len(set(ids))

    def test_equipamentos_referem_ativos_validos(self):
        ativos_ids = {a["id"] for a in ATIVOS}
        for eq in EQUIPAMENTOS:
            assert eq["ativo"] in ativos_ids, (
                f"Equipamento {eq['id']} refere ativo inexistente {eq['ativo']}"
            )

    def test_ativos_referem_sistemas_validos(self):
        sistemas_ids = {s["id"] for s in SISTEMAS}
        for atv in ATIVOS:
            assert atv["sistema"] in sistemas_ids, (
                f"Ativo {atv['id']} refere sistema inexistente {atv['sistema']}"
            )

    def test_equipamentos_referem_classes_validas(self):
        classes_fixture = {c["classe_id"] for c in carregar_classes_taxonomia()}
        for eq in EQUIPAMENTOS:
            assert eq["classe"] in classes_fixture, (
                f"Equipamento {eq['id']} refere classe inexistente {eq['classe']}"
            )

    def test_pelo_menos_20_equipamentos(self):
        assert len(EQUIPAMENTOS) >= 20

    def test_pelo_menos_5_sistemas(self):
        assert len(SISTEMAS) >= 5

    def test_pelo_menos_7_ativos(self):
        assert len(ATIVOS) >= 7


class TestVocabularioNeutro:
    """Vocabulario setorial nunca aparece em propriedades de no (regra 3)."""

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
        modos = carregar_modos_falha()
        classes_planta = {eq["classe"] for eq in EQUIPAMENTOS}
        sem_modo = []
        for classe_id in classes_planta:
            aplicaveis = _modos_para_classe(modos, classe_id)
            if not aplicaveis:
                sem_modo.append(classe_id)
        assert not sem_modo, f"Classes sem modo de falha aplicavel: {sem_modo}"


class TestGeracaoEventos:
    """Verifica que a geracao de eventos funciona para toda classe da planta."""

    def test_gera_historico_para_cada_classe(self):
        rng = np.random.default_rng(7)
        lambdas = carregar_lambda_verdadeiro()
        eq_por_classe = _equipamentos_por_classe()

        for classe_id, eqs in eq_por_classe.items():
            lambda_v = lambdas[classe_id]
            for eq in eqs:
                hist = gerar_historico(
                    classe_id=classe_id,
                    lambda_por_hora_op=lambda_v,
                    n_meses=24,
                    perfil=PERFIL_UNIFORME,
                    rng=rng,
                    n_equipamentos=1,
                )
                assert hist.horas_operacao_total > 0

    def test_numero_total_eventos_razoavel(self):
        rng = np.random.default_rng(7)
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
                    perfil=PERFIL_UNIFORME,
                    rng=rng,
                    n_equipamentos=1,
                )
                total += len(hist.eventos)

        assert 50 < total < 5000, f"Total de eventos ({total}) fora do esperado"


class TestDefeitos:
    """Validacao dos defeitos abertos."""

    def test_tres_defeitos(self):
        assert len(DEFEITOS) == 3

    def test_ids_unicos(self):
        ids = [d["id"] for d in DEFEITOS]
        assert len(ids) == len(set(ids))

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

    def test_causas_defeitos_sao_validas(self):
        causas = carregar_causas_falha()
        causas_ids = {c["codigo"] for c in causas}
        for d in DEFEITOS:
            assert d["causa"] in causas_ids, (
                f"Defeito {d['id']} usa causa inexistente {d['causa']}"
            )

    def test_mecanismos_defeitos_sao_validos(self):
        mecanismos = carregar_mecanismos_falha()
        mecanismos_ids = {m["codigo"] for m in mecanismos}
        for d in DEFEITOS:
            assert d["mecanismo"] in mecanismos_ids, (
                f"Defeito {d['id']} usa mecanismo inexistente {d['mecanismo']}"
            )

    def test_defeitos_referem_modos_do_catalogo_acoes(self):
        from seed.generator.fixtures_loader import carregar_acoes_permitidas
        acoes = carregar_acoes_permitidas()
        modos_no_catalogo = set()
        for acao in acoes:
            modos_no_catalogo.update(acao["modos_aplicaveis"])
        for d in DEFEITOS:
            assert d["modo"] in modos_no_catalogo, (
                f"Defeito {d['id']} usa modo {d['modo']} que nao tem acao no catalogo"
            )


class TestTopologia:
    """Validacao de ALIMENTA e REDUNDA_COM."""

    def test_alimenta_refere_ativos_validos(self):
        ativos_ids = {a["id"] for a in ATIVOS}
        for origem, destino in ALIMENTA:
            assert origem in ativos_ids, f"ALIMENTA origem {origem} inexistente"
            assert destino in ativos_ids, f"ALIMENTA destino {destino} inexistente"

    def test_redunda_com_tem_capacidade(self):
        for a1, a2, cap in REDUNDA_COM:
            assert 0.0 < cap <= 1.0, f"Capacidade {cap} fora do intervalo (0, 1]"

    def test_redunda_com_refere_ativos_validos(self):
        ativos_ids = {a["id"] for a in ATIVOS}
        for a1, a2, cap in REDUNDA_COM:
            assert a1 in ativos_ids, f"REDUNDA_COM {a1} inexistente"
            assert a2 in ativos_ids, f"REDUNDA_COM {a2} inexistente"

    def test_caminho_contrato_ate_ativo(self):
        assert CONTRATO["id"]
        assert ENTREGA["id"]
        assert PROCESSO["id"]
        assert len(FUNCOES) > 0
        fun_ativos = {f["ativo"] for f in FUNCOES}
        ativos_ids = {a["id"] for a in ATIVOS}
        assert fun_ativos.issubset(ativos_ids)


class TestPerfil:
    """Perfil de operacao uniforme (24/7)."""

    def test_perfil_uniforme_730h(self):
        for horas in PERFIL_UNIFORME.horas_por_mes:
            assert horas == 730.0


class TestContadores:
    """Contadores de evento nao colidem com agro."""

    def test_evento_counter_inicia_acima_de_5000(self):
        from seed.eletrico.seeder import SEED as SEED_EL
        assert SEED_EL != 2, "Semente eletrica deve diferir da agro"


class TestCatalogoAcoesPermitidas:
    """Validacao do catalogo AcaoPermitida no seeder eletrico."""

    def test_tres_papeis(self):
        assert len(PAPEIS) == 3

    def test_papeis_ids_unicos(self):
        ids = [p["id"] for p in PAPEIS]
        assert len(ids) == len(set(ids))

    def test_autorizacao_hierarquica(self):
        baixa = set(AUTORIZACAO_POR_COMPLEXIDADE["baixa"])
        media = set(AUTORIZACAO_POR_COMPLEXIDADE["media"])
        alta = set(AUTORIZACAO_POR_COMPLEXIDADE["alta"])
        assert alta.issubset(media)
        assert media.issubset(baixa)

    def test_viabilidade_decrescente(self):
        assert VIABILIDADE_POR_COMPLEXIDADE["baixa"] > VIABILIDADE_POR_COMPLEXIDADE["media"]
        assert VIABILIDADE_POR_COMPLEXIDADE["media"] > VIABILIDADE_POR_COMPLEXIDADE["alta"]


class TestFuncoesProcessos:
    """Validacao de funcoes e processos."""

    def test_funcoes_referem_ativos_validos(self):
        ativos_ids = {a["id"] for a in ATIVOS}
        for fun in FUNCOES:
            assert fun["ativo"] in ativos_ids, (
                f"Funcao {fun['id']} refere ativo inexistente {fun['ativo']}"
            )

    def test_ids_funcoes_unicos(self):
        ids = [f["id"] for f in FUNCOES]
        assert len(ids) == len(set(ids))

    def test_cada_ativo_tem_funcao(self):
        ativos_com_funcao = {f["ativo"] for f in FUNCOES}
        ativos_ids = {a["id"] for a in ATIVOS}
        sem_funcao = ativos_ids - ativos_com_funcao
        assert not sem_funcao, f"Ativos sem funcao: {sem_funcao}"
