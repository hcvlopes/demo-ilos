"""Gerador de EventoFalha por processo de Poisson não-homogêneo.

Gera eventos de falha respeitando:
- λ por hora de operação (nunca por hora de calendário)
- Perfil de sazonalidade (horas de operação por mês)
- Semente fixa para reprodutibilidade

Trabalha em memória — não grava no grafo (gravar é responsabilidade do seeder).
"""

from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator


@dataclass
class PerfilSazonalidade:
    """Horas de operação por mês (jan=0 a dez=11).

    Para equipamento sem sazonalidade, todos os meses iguais.
    Para agro, concentra em safra (mar–set no Centro-Oeste).
    """

    horas_por_mes: list[float]

    @property
    def total_anual(self) -> float:
        return sum(self.horas_por_mes)

    def horas_no_mes(self, mes: int) -> float:
        return self.horas_por_mes[mes % 12]


PERFIL_UNIFORME = PerfilSazonalidade(horas_por_mes=[730.0] * 12)

PERFIL_SAFRA_AGRO = PerfilSazonalidade(
    horas_por_mes=[
        200.0,   # jan — entressafra
        250.0,   # fev — início preparo
        650.0,   # mar — safra
        720.0,   # abr — safra plena
        720.0,   # mai — safra plena
        720.0,   # jun — safra plena
        700.0,   # jul — safra
        680.0,   # ago — safra
        500.0,   # set — fim safra
        300.0,   # out — entressafra
        200.0,   # nov — entressafra
        200.0,   # dez — entressafra
    ]
)


@dataclass
class EventoFalhaGerado:
    """Evento de falha gerado pelo processo de Poisson."""

    classe_id: str
    timestamp_horas_operacao: float
    ano: int
    mes: int
    hora_calendario: float


@dataclass
class HistoricoGerado:
    """Histórico completo para uma classe taxonômica."""

    classe_id: str
    lambda_verdadeiro: float
    eventos: list[EventoFalhaGerado] = field(default_factory=list)
    horas_operacao_total: float = 0.0
    horas_calendario_total: float = 0.0
    meses: int = 0


def gerar_historico(
    classe_id: str,
    lambda_por_hora_op: float,
    n_meses: int,
    perfil: PerfilSazonalidade,
    rng: Generator,
    n_equipamentos: int = 1,
    ano_inicio: int = 2024,
    mes_inicio: int = 1,
) -> HistoricoGerado:
    """Gera histórico de falhas via Poisson não-homogêneo.

    Para cada mês, o número esperado de falhas é λ × horas_operação_no_mês × n_equipamentos.
    A exposição total é n_equipamentos × horas_operação, modelando uma frota.
    Eventos são gerados por Poisson e distribuídos uniformemente dentro do mês.
    """
    historico = HistoricoGerado(
        classe_id=classe_id,
        lambda_verdadeiro=lambda_por_hora_op,
        meses=n_meses,
    )

    hora_calendario_acum = 0.0
    hora_operacao_acum = 0.0

    for i in range(n_meses):
        ano = ano_inicio + (mes_inicio - 1 + i) // 12
        mes = (mes_inicio - 1 + i) % 12

        horas_op_mes = perfil.horas_no_mes(mes)
        horas_cal_mes = 730.0  # ~365.25*24/12

        lambda_mes = lambda_por_hora_op * horas_op_mes * n_equipamentos
        n_eventos = rng.poisson(lambda_mes)

        for _ in range(n_eventos):
            t_dentro_mes = rng.uniform(0, horas_op_mes)
            historico.eventos.append(
                EventoFalhaGerado(
                    classe_id=classe_id,
                    timestamp_horas_operacao=hora_operacao_acum + t_dentro_mes,
                    ano=ano,
                    mes=mes + 1,
                    hora_calendario=hora_calendario_acum
                    + (t_dentro_mes / horas_op_mes) * horas_cal_mes,
                )
            )

        hora_operacao_acum += horas_op_mes * n_equipamentos
        hora_calendario_acum += horas_cal_mes * n_equipamentos

    historico.horas_operacao_total = hora_operacao_acum
    historico.horas_calendario_total = hora_calendario_acum

    historico.eventos.sort(key=lambda e: e.timestamp_horas_operacao)
    return historico
