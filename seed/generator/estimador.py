"""Estimador de λ com intervalo de confiança.

Estima a taxa de falha (λ) a partir do histórico gerado e calcula o
intervalo de confiança usando a relação exata com a distribuição chi-quadrado:
  IC = [χ²(α/2, 2n) / (2T), χ²(1−α/2, 2n+2) / (2T)]

onde n = número de falhas e T = tempo total de operação.

Referência: ISO 14224:2016 Seção 9.3, MIL-HDBK-217.
"""

from dataclasses import dataclass

from scipy.stats import chi2

from seed.generator.poisson import HistoricoGerado


@dataclass
class EstimativaLambda:
    """Resultado da estimativa de λ."""

    classe_id: str
    lambda_hat: float
    ic_inferior: float
    ic_superior: float
    n_eventos: int
    horas_operacao: float
    nivel_confianca: float
    largura_relativa: float


def estimar_lambda(
    historico: HistoricoGerado,
    nivel_confianca: float = 0.95,
) -> EstimativaLambda:
    """Estima λ por MLE com IC exato via chi-quadrado."""
    n = len(historico.eventos)
    T = historico.horas_operacao_total

    if T <= 0:
        raise ValueError("Tempo de operação deve ser positivo")

    lambda_hat = n / T if n > 0 else 0.0

    alpha = 1.0 - nivel_confianca

    if n == 0:
        ic_inferior = 0.0
        ic_superior = chi2.ppf(1 - alpha / 2, 2) / (2 * T)
    else:
        ic_inferior = chi2.ppf(alpha / 2, 2 * n) / (2 * T)
        ic_superior = chi2.ppf(1 - alpha / 2, 2 * n + 2) / (2 * T)

    largura = ic_superior - ic_inferior
    largura_relativa = largura / lambda_hat if lambda_hat > 0 else float("inf")

    return EstimativaLambda(
        classe_id=historico.classe_id,
        lambda_hat=lambda_hat,
        ic_inferior=ic_inferior,
        ic_superior=ic_superior,
        n_eventos=n,
        horas_operacao=T,
        nivel_confianca=nivel_confianca,
        largura_relativa=largura_relativa,
    )


def estimar_lambda_calendario(
    historico: HistoricoGerado,
    nivel_confianca: float = 0.95,
) -> EstimativaLambda:
    """Estima λ por hora de CALENDÁRIO (para comparação com hora de operação)."""
    n = len(historico.eventos)
    T_cal = historico.horas_calendario_total

    if T_cal <= 0:
        raise ValueError("Tempo de calendário deve ser positivo")

    lambda_hat = n / T_cal if n > 0 else 0.0

    alpha = 1.0 - nivel_confianca

    if n == 0:
        ic_inferior = 0.0
        ic_superior = chi2.ppf(1 - alpha / 2, 2) / (2 * T_cal)
    else:
        ic_inferior = chi2.ppf(alpha / 2, 2 * n) / (2 * T_cal)
        ic_superior = chi2.ppf(1 - alpha / 2, 2 * n + 2) / (2 * T_cal)

    largura = ic_superior - ic_inferior
    largura_relativa = largura / lambda_hat if lambda_hat > 0 else float("inf")

    return EstimativaLambda(
        classe_id=historico.classe_id,
        lambda_hat=lambda_hat,
        ic_inferior=ic_inferior,
        ic_superior=ic_superior,
        n_eventos=n,
        horas_operacao=T_cal,
        nivel_confianca=nivel_confianca,
        largura_relativa=largura_relativa,
    )
