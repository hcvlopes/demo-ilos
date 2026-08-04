from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    resolver_no,
)


class ExposicaoProcessoParams(BaseModel):
    processo_id: str = ""


class ExposicaoProcesso(IntencaoBase):
    """Regime de operacao do processo e o efeito disso na taxa de falha.

    Existe para tornar a regra 7 do CLAUDE.md consultavel, nao apenas
    respeitada no codigo. O regime vivia no perfil de Poisson do seeder; com
    `horas_operacao_ano` e `horas_calendario_ano` no grafo, da para mostrar o
    tamanho do erro que se comete ao usar hora de calendario: num processo
    sazonal de 5.840 h/ano, lambda por calendario subestima a taxa em 1,5x.

    E o argumento fica quantificado em vez de assertivo.
    """

    nome = "exposicao_processo"
    descricao = (
        "Mostra o regime de operacao de um processo, as horas de exposicao por "
        "ano e o erro de calcular taxa de falha por hora de calendario"
    )

    def executar(self, session, params: ExposicaoProcessoParams) -> EnvelopeEvidencia:
        proc = resolver_no(session, "ProcessoOperacional", params.processo_id)
        pid = proc["id"]

        h_op = proc.get("horas_operacao_ano")
        h_cal = proc.get("horas_calendario_ano")
        regime = proc.get("regime")
        razao = proc.get("razao_pico_vale")

        nos = [NoEvidencia(
            label="ProcessoOperacional", id=pid,
            propriedades={
                "descricao": proc.get("descricao", ""),
                "regime": regime or "", "horas_operacao_ano": h_op or "",
                "horas_calendario_ano": h_cal or "", "razao_pico_vale": razao or "",
            },
        )]
        arestas = []
        ids_vistos = {pid}

        # Metrica agregada do processo, para dizer o lambda nas duas bases.
        r = session.run(
            """
            MATCH (p:ProcessoOperacional {id: $pid})-[:REQUER]->(:Funcao)
                  <-[:DESEMPENHA]-(:Ativo)<-[:PERTENCE]-(eq:Equipamento)
            MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)-[:TEM_METRICA]->(m:MetricaConfiabilidade)
            RETURN sum(m.lambda_hat) AS lam, sum(m.ic_inferior) AS ic_inf,
                   sum(m.ic_superior) AS ic_sup, count(DISTINCT eq) AS equipamentos
            """,
            parameters={"pid": pid},
        ).single()
        lam = float(r["lam"]) if r and r["lam"] else None
        equipamentos = int(r["equipamentos"]) if r and r["equipamentos"] else 0

        calculos = []
        if h_op:
            calculos.append(CalculoEvidencia(
                nome="horas_operacao_ano", formula="perfil de sazonalidade do setor",
                valor=float(h_op), unidade="horas/ano",
            ))
        if h_cal:
            calculos.append(CalculoEvidencia(
                nome="horas_calendario_ano", formula="365 x 24",
                valor=float(h_cal), unidade="horas/ano",
            ))
        fator = None
        if h_op and h_cal:
            fator = float(h_cal) / float(h_op)
            calculos.append(CalculoEvidencia(
                nome="fator_de_subestimacao",
                formula="horas_calendario_ano / horas_operacao_ano",
                valor=round(fator, 3), unidade="x",
            ))
        if razao:
            calculos.append(CalculoEvidencia(
                nome="razao_pico_vale", formula="maior mes / menor mes de operacao",
                valor=float(razao), unidade="x",
            ))
        if lam:
            calculos.append(CalculoEvidencia(
                nome="lambda_por_hora_operacao",
                formula="soma(lambda_hat das classes do processo)",
                valor=round(lam, 8), unidade="falhas/h_op",
                ic_inferior=round(float(r["ic_inf"]), 8) if r["ic_inf"] else None,
                ic_superior=round(float(r["ic_sup"]), 8) if r["ic_sup"] else None,
            ))
            if fator:
                calculos.append(CalculoEvidencia(
                    nome="lambda_se_fosse_por_calendario",
                    formula="lambda_por_hora_operacao / fator_de_subestimacao",
                    valor=round(lam / fator, 8), unidade="falhas/h_cal",
                ))

        # Ativos do processo entram como evidencia do que compoe a exposicao.
        for reg in session.run(
            """
            MATCH (p:ProcessoOperacional {id: $pid})-[:REQUER]->(f:Funcao)<-[:DESEMPENHA]-(a:Ativo)
            RETURN a, f ORDER BY a.id
            """,
            parameters={"pid": pid},
        ):
            for no, label in [(reg["a"], "Ativo"), (reg["f"], "Funcao")]:
                if no["id"] not in ids_vistos:
                    ids_vistos.add(no["id"])
                    nos.append(NoEvidencia(
                        label=label, id=no["id"],
                        propriedades={"descricao": no.get("descricao", "")},
                    ))
            arestas.append(ArestaEvidencia(
                tipo="DESEMPENHA", origem_id=reg["a"]["id"], destino_id=reg["f"]["id"],
            ))

        lacunas = []
        if not regime:
            lacunas.append("Processo sem regime de operacao declarado.")
        if not h_op:
            lacunas.append(
                "Sem horas de operacao declaradas, a taxa de falha nao pode ser "
                "expressa por hora de exposicao (regra 7).",
            )
        if lam:
            lacunas.append(
                "O intervalo e a soma dos limites das classes: limite "
                "conservador, nao IC exato.",
            )

        if fator and fator > 1.01:
            fecho = (
                f"Calcular a taxa de falha por hora de calendario subestimaria "
                f"a exposicao em {fator:.2f}x."
            )
        elif fator:
            fecho = (
                "Como a operacao e continua, hora de operacao e hora de "
                "calendario coincidem."
            )
        else:
            fecho = "Sem horas declaradas, o efeito do regime nao e quantificavel."

        return EnvelopeEvidencia(
            afirmacao=(
                f"O processo {proc.get('descricao', pid)} opera em regime "
                f"{regime or 'nao declarado'}, com {h_op or '?'} horas de operacao por ano "
                f"em {equipamentos} equipamento(s). {fecho}"
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
