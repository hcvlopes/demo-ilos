"""Motor de escore de risco — F5.

Escore = P(falha na janela | defeito aberto, lambda da classe)
       x impacto(processo -> entrega -> contrato)
       x (1 - fator_redundancia)

P(falha) usa modelo exponencial: 1 - exp(-lambda * t).
Impacto = 1 + n_downstream (ativos alcancaveis via ALIMENTA).
Redundancia = capacidade da aresta REDUNDA_COM (0 se nao ha redundancia).
"""

import math
from dataclasses import dataclass, field


@dataclass
class EscoreRisco:
    """Resultado do calculo de escore de risco para um ativo."""

    ativo_id: str
    escore: float
    p_falha: float
    impacto: float
    fator_redundancia: float
    lambda_hat: float
    janela_horas: float
    ic_inferior_lambda: float
    ic_superior_lambda: float
    defeitos_abertos: list[str] = field(default_factory=list)


def probabilidade_falha(lambda_hat: float, janela_horas: float) -> float:
    """P(>=1 falha na janela) = 1 - e^(-lambda*t) para processo de Poisson."""
    if lambda_hat <= 0 or janela_horas <= 0:
        return 0.0
    return 1.0 - math.exp(-lambda_hat * janela_horas)


def calcular_impacto(n_downstream: int) -> float:
    """Fator de impacto baseado em ativos downstream via ALIMENTA."""
    return float(1 + max(0, n_downstream))


def calcular_escore(
    p_falha: float,
    impacto: float,
    fator_redundancia: float,
) -> float:
    """Escore de risco = P(falha) x impacto x (1 - redundancia)."""
    red = max(0.0, min(1.0, fator_redundancia))
    return p_falha * impacto * (1.0 - red)
