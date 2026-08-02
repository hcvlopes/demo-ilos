"""Teste de calibração (F2) — o critério mais importante do projeto.

Dado lambda verdadeiro por classe em fixtures/calibracao/lambda_verdadeiro.yaml,
o gerador produz 24 meses de eventos e o estimador recupera lambda dentro do
IC 95% para toda classe taxonômica.

Testes determinísticos com semente fixa.
"""

import numpy as np
import pytest

from seed.generator.estimador import estimar_lambda, estimar_lambda_calendario
from seed.generator.fixtures_loader import carregar_lambda_verdadeiro
from seed.generator.poisson import (
    PERFIL_SAFRA_AGRO,
    PERFIL_UNIFORME,
    gerar_historico,
)

SEED = 2
N_MESES = 24
LARGURA_RELATIVA_MAX = 1.5

# Frota por classe — equipamentos com λ baixo precisam de mais instâncias
# para gerar volume estatístico suficiente em 24 meses.
FROTA_POR_CLASSE: dict[str, int] = {
    "CT-BCC": 5,    # bombas centrífugas: λ alto, frota média
    "CT-BCP": 3,    # bombas de pistão: λ alto
    "CT-CMP": 3,    # compressores
    "CT-MOE": 20,   # motores elétricos: λ baixo, frota grande
    "CT-VCT": 15,   # válvulas de controle
    "CT-VSG": 10,   # PSVs
    "CT-VMA": 50,   # válvulas manuais: λ muito baixo, frota grande
    "CT-VEN": 6,    # ventiladores
    "CT-TRF": 15,   # transformadores: λ muito baixo, frota grande
    "CT-DJT": 20,   # disjuntores: λ baixo
    "CT-TCL": 10,   # trocadores de calor
    "CT-TRE": 4,    # transportadores
    "CT-ELB": 4,    # elevadores de canecas
    "CT-SEC": 8,    # secadores
    "CT-GER": 8,    # geradores
}


@pytest.fixture
def lambdas_verdadeiros():
    return carregar_lambda_verdadeiro()


@pytest.fixture
def rng():
    return np.random.default_rng(SEED)


class TestRecuperacaoLambda:
    """Lambda estimado recupera lambda verdadeiro dentro do IC 95%."""

    def test_todas_classes_dentro_do_ic(self, lambdas_verdadeiros, rng):
        """Para toda classe, λ verdadeiro cai dentro do IC 95%."""
        falhas = []
        for classe_id, lambda_v in lambdas_verdadeiros.items():
            historico = gerar_historico(
                classe_id=classe_id,
                lambda_por_hora_op=lambda_v,
                n_meses=N_MESES,
                perfil=PERFIL_UNIFORME,
                rng=rng,
                n_equipamentos=FROTA_POR_CLASSE.get(classe_id, 5),
            )
            est = estimar_lambda(historico)

            if not (est.ic_inferior <= lambda_v <= est.ic_superior):
                falhas.append(
                    f"{classe_id}: λ_v={lambda_v:.6f} fora do IC "
                    f"[{est.ic_inferior:.6f}, {est.ic_superior:.6f}] "
                    f"(λ_hat={est.lambda_hat:.6f}, n={est.n_eventos})"
                )

        assert not falhas, (
            f"Lambda verdadeiro fora do IC 95% em {len(falhas)} classe(s):\n"
            + "\n".join(falhas)
        )

    def test_determinismo_com_semente_fixa(self, lambdas_verdadeiros):
        """Duas execuções com mesma semente produzem resultado idêntico."""
        resultados = []
        for _ in range(2):
            rng = np.random.default_rng(SEED)
            contagens = {}
            for classe_id, lambda_v in lambdas_verdadeiros.items():
                hist = gerar_historico(
                    classe_id=classe_id,
                    lambda_por_hora_op=lambda_v,
                    n_meses=N_MESES,
                    perfil=PERFIL_UNIFORME,
                    rng=rng,
                    n_equipamentos=FROTA_POR_CLASSE.get(classe_id, 5),
                )
                contagens[classe_id] = len(hist.eventos)
            resultados.append(contagens)

        assert resultados[0] == resultados[1]

    def test_largura_relativa_ic_aceitavel(self, lambdas_verdadeiros, rng):
        """IC não é excessivamente largo — volume de histórico é suficiente."""
        problemas = []
        for classe_id, lambda_v in lambdas_verdadeiros.items():
            historico = gerar_historico(
                classe_id=classe_id,
                lambda_por_hora_op=lambda_v,
                n_meses=N_MESES,
                perfil=PERFIL_UNIFORME,
                rng=rng,
                n_equipamentos=FROTA_POR_CLASSE.get(classe_id, 5),
            )
            est = estimar_lambda(historico)

            if est.largura_relativa > LARGURA_RELATIVA_MAX:
                problemas.append(
                    f"{classe_id}: largura_relativa={est.largura_relativa:.2f} "
                    f"> {LARGURA_RELATIVA_MAX} (n={est.n_eventos})"
                )

        assert not problemas, (
            f"IC excessivamente largo em {len(problemas)} classe(s) "
            f"— volume de histórico insuficiente:\n" + "\n".join(problemas)
        )


class TestSazonalidadeAgro:
    """Exposição sazonal: λ/h operação ≠ λ/h calendário."""

    def test_lambda_operacao_difere_de_calendario(self, lambdas_verdadeiros, rng):
        """Com perfil sazonal, λ estimado por hora de operação difere
        significativamente de λ estimado por hora de calendário."""
        classe_id = "CT-BCC"
        lambda_v = lambdas_verdadeiros[classe_id]

        historico = gerar_historico(
            classe_id=classe_id,
            lambda_por_hora_op=lambda_v,
            n_meses=N_MESES,
            perfil=PERFIL_SAFRA_AGRO,
            rng=rng,
            n_equipamentos=FROTA_POR_CLASSE.get(classe_id, 5),
        )

        est_op = estimar_lambda(historico)
        est_cal = estimar_lambda_calendario(historico)

        assert est_op.lambda_hat != pytest.approx(
            est_cal.lambda_hat, rel=0.01
        ), (
            f"λ por hora de operação ({est_op.lambda_hat:.6f}) não deveria ser "
            f"igual a λ por hora de calendário ({est_cal.lambda_hat:.6f}) "
            f"com perfil sazonal"
        )

    def test_fator_sazonalidade_esperado(self, lambdas_verdadeiros, rng):
        """O fator entre λ_calendario e λ_operacao reflete a razão
        horas_operacao / horas_calendario do perfil sazonal."""
        classe_id = "CT-BCC"
        lambda_v = lambdas_verdadeiros[classe_id]

        historico = gerar_historico(
            classe_id=classe_id,
            lambda_por_hora_op=lambda_v,
            n_meses=N_MESES,
            perfil=PERFIL_SAFRA_AGRO,
            rng=rng,
            n_equipamentos=FROTA_POR_CLASSE.get(classe_id, 5),
        )

        est_op = estimar_lambda(historico)
        est_cal = estimar_lambda_calendario(historico)

        fator_horas = (
            PERFIL_SAFRA_AGRO.total_anual / PERFIL_UNIFORME.total_anual
        )

        fator_lambda = est_cal.lambda_hat / est_op.lambda_hat

        assert fator_lambda == pytest.approx(fator_horas, rel=0.05), (
            f"Fator λ_cal/λ_op = {fator_lambda:.4f}, esperado ≈ {fator_horas:.4f} "
            f"(razão horas_op/horas_cal do perfil sazonal)"
        )

    def test_lambda_verdadeiro_dentro_ic_com_sazonalidade(
        self, lambdas_verdadeiros, rng
    ):
        """Mesmo com sazonalidade, o estimador por hora de operação
        recupera λ verdadeiro dentro do IC."""
        falhas = []
        for classe_id, lambda_v in lambdas_verdadeiros.items():
            historico = gerar_historico(
                classe_id=classe_id,
                lambda_por_hora_op=lambda_v,
                n_meses=N_MESES,
                perfil=PERFIL_SAFRA_AGRO,
                rng=rng,
                n_equipamentos=FROTA_POR_CLASSE.get(classe_id, 5),
            )
            est_op = estimar_lambda(historico)

            if not (est_op.ic_inferior <= lambda_v <= est_op.ic_superior):
                falhas.append(
                    f"{classe_id}: λ_v={lambda_v:.6f} fora do IC "
                    f"[{est_op.ic_inferior:.6f}, {est_op.ic_superior:.6f}]"
                )

        assert not falhas, (
            f"Com sazonalidade, λ_v fora do IC em {len(falhas)} classe(s):\n"
            + "\n".join(falhas)
        )


class TestGerador:
    """Testes do gerador de histórico."""

    def test_historico_vazio_para_lambda_zero(self, rng):
        """λ = 0 produz zero eventos."""
        hist = gerar_historico("TESTE", 0.0, 12, PERFIL_UNIFORME, rng)
        assert len(hist.eventos) == 0

    def test_eventos_ordenados_por_hora_operacao(self, rng):
        """Eventos saem ordenados por timestamp de hora de operação."""
        hist = gerar_historico("CT-BCC", 0.001, 24, PERFIL_UNIFORME, rng)
        timestamps = [e.timestamp_horas_operacao for e in hist.eventos]
        assert timestamps == sorted(timestamps)

    def test_horas_operacao_total_corretas(self, rng):
        """Total de horas de operação é soma do perfil × meses × n_equipamentos."""
        n_meses = 12
        n_eq = 3
        hist = gerar_historico("TESTE", 0.001, n_meses, PERFIL_SAFRA_AGRO, rng, n_equipamentos=n_eq)
        esperado = PERFIL_SAFRA_AGRO.total_anual * n_eq
        assert hist.horas_operacao_total == pytest.approx(esperado, rel=1e-6)

    def test_mais_eventos_em_meses_de_safra(self, rng):
        """Com perfil sazonal, mais falhas ocorrem nos meses de safra."""
        hist = gerar_historico("CT-BCC", 0.002, 24, PERFIL_SAFRA_AGRO, rng)

        safra = sum(1 for e in hist.eventos if e.mes in (3, 4, 5, 6, 7, 8))
        entressafra = sum(1 for e in hist.eventos if e.mes in (1, 10, 11, 12))

        assert safra > entressafra, (
            f"Safra ({safra}) deveria ter mais eventos que entressafra ({entressafra})"
        )
