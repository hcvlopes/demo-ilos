"""Intenção: historico_equipamento.

Dado um equipamento_id, percorre o grafo para devolver histórico de falhas,
manutenções, métricas de confiabilidade e normas aplicáveis.
"""

from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)


class HistoricoEquipamentoParams(BaseModel):
    equipamento_id: str


class HistoricoEquipamento(IntencaoBase):
    nome = "historico_equipamento"
    descricao = "Historico de falhas, manutencoes e metricas de um equipamento"

    def executar(self, session, params: HistoricoEquipamentoParams) -> EnvelopeEvidencia:
        # Equipamento, classe e métrica
        base = session.run(
            """
            MATCH (eq:Equipamento {id: $id})-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
            OPTIONAL MATCH (ct)-[:REGULADO_POR]->(n:Norma)
            RETURN eq, ct, mc, n
            """,
            {"id": params.equipamento_id},
        ).single()

        if base is None:
            return EnvelopeEvidencia(
                afirmacao=f"Equipamento {params.equipamento_id} nao encontrado.",
                nos=[],
                arestas=[],
                calculos=[],
                normas=[],
                lacunas=[f"Equipamento {params.equipamento_id} inexistente"],
            )

        eq = base["eq"]
        ct = base["ct"]
        mc = base["mc"]
        norma = base["n"]

        nos = [
            NoEvidencia(label="Equipamento", id=eq["id"], propriedades=dict(eq)),
            NoEvidencia(label="ClasseTaxonomia", id=ct["id"], propriedades=dict(ct)),
        ]
        arestas = [
            ArestaEvidencia(tipo="CLASSIFICADO_COMO", origem_id=eq["id"], destino_id=ct["id"]),
        ]

        # Eventos de falha
        eventos = session.run(
            """
            MATCH (ef:EventoFalha)-[:OCORREU]->(eq:Equipamento {id: $id})
            OPTIONAL MATCH (ef)-[:MANIFESTOU]->(mf:ModoFalha)
            OPTIONAL MATCH (ef)-[:CAUSADO_POR]->(cf:CausaFalha)
            RETURN ef, mf, cf
            ORDER BY ef.timestamp_horas_operacao
            """,
            {"id": params.equipamento_id},
        )

        n_eventos = 0
        for record in eventos:
            ef = record["ef"]
            mf = record["mf"]
            cf = record["cf"]
            n_eventos += 1

            nos.append(NoEvidencia(label="EventoFalha", id=ef["id"], propriedades=dict(ef)))
            arestas.append(ArestaEvidencia(tipo="OCORREU", origem_id=ef["id"], destino_id=eq["id"]))

            if mf is not None:
                no_mf = NoEvidencia(label="ModoFalha", id=mf["id"], propriedades=dict(mf))
                if no_mf not in nos:
                    nos.append(no_mf)
                arestas.append(ArestaEvidencia(tipo="MANIFESTOU", origem_id=ef["id"], destino_id=mf["id"]))

            if cf is not None:
                no_cf = NoEvidencia(label="CausaFalha", id=cf["id"], propriedades=dict(cf))
                if no_cf not in nos:
                    nos.append(no_cf)
                arestas.append(ArestaEvidencia(tipo="CAUSADO_POR", origem_id=ef["id"], destino_id=cf["id"]))

        # Ordens de manutenção
        ordens = session.run(
            """
            MATCH (om:OrdemManutencao)-[:EXECUTADA_EM]->(eq:Equipamento {id: $id})
            RETURN om
            """,
            {"id": params.equipamento_id},
        )
        n_ordens = 0
        for record in ordens:
            om = record["om"]
            n_ordens += 1
            nos.append(NoEvidencia(label="OrdemManutencao", id=om["id"], propriedades=dict(om)))
            arestas.append(ArestaEvidencia(tipo="EXECUTADA_EM", origem_id=om["id"], destino_id=eq["id"]))

        calculos = []
        if mc is not None:
            nos.append(NoEvidencia(label="MetricaConfiabilidade", id=mc["id"], propriedades=dict(mc)))
            arestas.append(ArestaEvidencia(tipo="TEM_METRICA", origem_id=ct["id"], destino_id=mc["id"]))
            calculos.append(
                CalculoEvidencia(
                    nome="lambda_hat",
                    formula="n_eventos / horas_operacao",
                    valor=mc["lambda_hat"],
                    unidade="falhas/hora",
                    ic_inferior=mc["ic_inferior"],
                    ic_superior=mc["ic_superior"],
                )
            )

        normas = []
        if norma is not None:
            nos.append(NoEvidencia(label="Norma", id=norma["id"], propriedades=dict(norma)))
            arestas.append(ArestaEvidencia(tipo="REGULADO_POR", origem_id=ct["id"], destino_id=norma["id"]))
            normas.append(NormaEvidencia(codigo=norma.get("codigo", norma["id"]), descricao=norma.get("descricao", "")))

        lacunas = []
        if mc is None:
            lacunas.append("Metrica de confiabilidade nao calculada para esta classe")
        if n_eventos == 0:
            lacunas.append("Nenhum evento de falha registrado")
        if n_ordens == 0:
            lacunas.append("Nenhuma ordem de manutencao registrada")

        afirmacao = (
            f"Equipamento {eq['id']} ({ct['descricao']}): "
            f"{n_eventos} evento(s) de falha, {n_ordens} ordem(ns) de manutencao."
        )
        if mc is not None:
            afirmacao += (
                f" Lambda: {mc['lambda_hat']:.6f} falhas/hora "
                f"(IC 95%: [{mc['ic_inferior']:.6f}, {mc['ic_superior']:.6f}])."
            )

        return EnvelopeEvidencia(
            afirmacao=afirmacao,
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=normas,
            lacunas=lacunas,
        )
