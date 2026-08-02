"""Intencao: ativos_em_risco_por_processo (F5).

Dado um processo operacional e uma janela de tempo, calcula o escore de
risco para cada ativo com defeito aberto, ordenado do mais critico.

Escore = P(falha na janela | lambda da classe)
       x impacto(n_downstream via ALIMENTA)
       x (1 - fator_redundancia via REDUNDA_COM)
"""

from pydantic import BaseModel, Field

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)
from scoring.risco import (
    EscoreRisco,
    calcular_escore,
    calcular_impacto,
    probabilidade_falha,
)

JANELA_PADRAO_HORAS = 720.0


class AtivosEmRiscoParams(BaseModel):
    processo_id: str
    janela_horas: float = Field(default=JANELA_PADRAO_HORAS, gt=0)


class AtivosEmRiscoPorProcesso(IntencaoBase):
    nome = "ativos_em_risco_por_processo"
    descricao = "Ranking de ativos em risco por processo operacional"

    def executar(self, session, params: AtivosEmRiscoParams) -> EnvelopeEvidencia:
        processo = session.run(
            """
            MATCH (po:ProcessoOperacional {id: $id})
            OPTIONAL MATCH (po)<-[:VINCULADA]-(ent:Entrega)<-[:TEM_ENTREGA]-(con:Contrato)
            RETURN po, ent, con
            """,
            {"id": params.processo_id},
        ).single()

        if processo is None:
            return EnvelopeEvidencia(
                afirmacao=f"Processo {params.processo_id} nao encontrado.",
                nos=[],
                arestas=[],
                calculos=[],
                normas=[],
                lacunas=[f"Processo {params.processo_id} inexistente"],
            )

        po = processo["po"]
        ent = processo["ent"]
        con = processo["con"]

        nos = [NoEvidencia(label="ProcessoOperacional", id=po["id"], propriedades=dict(po))]
        arestas = []

        if ent is not None:
            nos.append(NoEvidencia(label="Entrega", id=ent["id"], propriedades=dict(ent)))
            arestas.append(ArestaEvidencia(tipo="VINCULADA", origem_id=ent["id"], destino_id=po["id"]))
        if con is not None:
            nos.append(NoEvidencia(label="Contrato", id=con["id"], propriedades=dict(con)))
            arestas.append(ArestaEvidencia(tipo="TEM_ENTREGA", origem_id=con["id"], destino_id=ent["id"]))

        ativos_result = session.run(
            """
            MATCH (po:ProcessoOperacional {id: $id})-[:REQUER]->(f:Funcao)<-[:DESEMPENHA]-(a:Ativo)
            RETURN a, f
            """,
            {"id": params.processo_id},
        )

        ativo_ids = []
        for record in ativos_result:
            a = record["a"]
            f = record["f"]
            ativo_ids.append(a["id"])
            no_a = NoEvidencia(label="Ativo", id=a["id"], propriedades=dict(a))
            if no_a not in nos:
                nos.append(no_a)
            no_f = NoEvidencia(label="Funcao", id=f["id"], propriedades=dict(f))
            if no_f not in nos:
                nos.append(no_f)
            arestas.append(ArestaEvidencia(tipo="REQUER", origem_id=po["id"], destino_id=f["id"]))
            arestas.append(ArestaEvidencia(tipo="DESEMPENHA", origem_id=a["id"], destino_id=f["id"]))

        escores: list[EscoreRisco] = []
        calculos = []
        normas_set: set[str] = set()
        normas = []

        for ativo_id in ativo_ids:
            escore = self._calcular_risco_ativo(
                session, ativo_id, params.janela_horas, nos, arestas, normas, normas_set,
            )
            if escore is not None:
                escores.append(escore)

        escores.sort(key=lambda e: e.escore, reverse=True)

        for rank, esc in enumerate(escores, 1):
            calculos.append(
                CalculoEvidencia(
                    nome=f"escore_risco_{esc.ativo_id}",
                    formula="P(falha) x impacto x (1 - redundancia)",
                    valor=esc.escore,
                    unidade="adimensional",
                    ic_inferior=probabilidade_falha(esc.ic_inferior_lambda, esc.janela_horas)
                    * esc.impacto
                    * (1.0 - esc.fator_redundancia),
                    ic_superior=probabilidade_falha(esc.ic_superior_lambda, esc.janela_horas)
                    * esc.impacto
                    * (1.0 - esc.fator_redundancia),
                )
            )

        lacunas = []
        if not escores:
            lacunas.append("Nenhum ativo com defeito aberto e metrica de confiabilidade")

        n_sem_metrica = len(ativo_ids) - len(escores)
        if n_sem_metrica > 0:
            lacunas.append(
                f"{n_sem_metrica} ativo(s) sem metrica de confiabilidade ou sem defeito aberto"
            )

        if escores:
            top = escores[0]
            afirmacao = (
                f"Processo {po['id']}: {len(escores)} ativo(s) em risco. "
                f"Mais critico: {top.ativo_id} (escore {top.escore:.4f}, "
                f"P(falha)={top.p_falha:.4f}, impacto={top.impacto:.0f}, "
                f"redundancia={top.fator_redundancia:.2f}). "
                f"Janela: {params.janela_horas:.0f}h."
            )
        else:
            afirmacao = (
                f"Processo {po['id']}: nenhum ativo em risco na janela de "
                f"{params.janela_horas:.0f}h."
            )

        return EnvelopeEvidencia(
            afirmacao=afirmacao,
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=normas,
            lacunas=lacunas,
        )

    def _calcular_risco_ativo(
        self,
        session,
        ativo_id: str,
        janela_horas: float,
        nos: list[NoEvidencia],
        arestas: list[ArestaEvidencia],
        normas: list[NormaEvidencia],
        normas_set: set[str],
    ) -> EscoreRisco | None:
        equip_result = session.run(
            """
            MATCH (a:Ativo {id: $id})<-[:PERTENCE]-(eq:Equipamento)
                  -[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
            OPTIONAL MATCH (df:Defeito {status: 'aberto'})-[:DETECTADO_EM]->(eq)
            OPTIONAL MATCH (ct)-[:REGULADO_POR]->(n:Norma)
            RETURN eq, ct, mc, collect(DISTINCT df) as defeitos, n
            """,
            {"id": ativo_id},
        )

        lambda_max = 0.0
        ic_inf_max = 0.0
        ic_sup_max = 0.0
        defeitos_ids: list[str] = []
        has_metrica = False

        for record in equip_result:
            eq = record["eq"]
            ct = record["ct"]
            mc = record["mc"]
            defeitos = record["defeitos"]
            norma = record["n"]

            no_eq = NoEvidencia(label="Equipamento", id=eq["id"], propriedades=dict(eq))
            if no_eq not in nos:
                nos.append(no_eq)
            no_ct = NoEvidencia(label="ClasseTaxonomia", id=ct["id"], propriedades=dict(ct))
            if no_ct not in nos:
                nos.append(no_ct)
            arestas.append(ArestaEvidencia(tipo="PERTENCE", origem_id=eq["id"], destino_id=ativo_id))
            arestas.append(ArestaEvidencia(tipo="CLASSIFICADO_COMO", origem_id=eq["id"], destino_id=ct["id"]))

            if norma is not None and norma["id"] not in normas_set:
                normas_set.add(norma["id"])
                nos.append(NoEvidencia(label="Norma", id=norma["id"], propriedades=dict(norma)))
                arestas.append(ArestaEvidencia(tipo="REGULADO_POR", origem_id=ct["id"], destino_id=norma["id"]))
                normas.append(NormaEvidencia(
                    codigo=norma.get("codigo", norma["id"]),
                    descricao=norma.get("descricao", ""),
                ))

            for df in defeitos:
                if df is not None and df["id"] not in defeitos_ids:
                    defeitos_ids.append(df["id"])
                    no_df = NoEvidencia(label="Defeito", id=df["id"], propriedades=dict(df))
                    if no_df not in nos:
                        nos.append(no_df)
                    arestas.append(ArestaEvidencia(tipo="DETECTADO_EM", origem_id=df["id"], destino_id=eq["id"]))

            if mc is not None:
                has_metrica = True
                no_mc = NoEvidencia(label="MetricaConfiabilidade", id=mc["id"], propriedades=dict(mc))
                if no_mc not in nos:
                    nos.append(no_mc)
                arestas.append(ArestaEvidencia(tipo="TEM_METRICA", origem_id=ct["id"], destino_id=mc["id"]))

                lh = mc["lambda_hat"]
                if lh > lambda_max:
                    lambda_max = lh
                    ic_inf_max = mc["ic_inferior"]
                    ic_sup_max = mc["ic_superior"]

        if not defeitos_ids or not has_metrica:
            return None

        downstream_result = session.run(
            """
            MATCH (a:Ativo {id: $id})-[:ALIMENTA*1..]->(d:Ativo)
            RETURN count(DISTINCT d) as n
            """,
            {"id": ativo_id},
        ).single()
        n_downstream = downstream_result["n"] if downstream_result else 0

        redundancia_result = session.run(
            """
            MATCH (a:Ativo {id: $id})-[r:REDUNDA_COM]-(:Ativo)
            RETURN r.capacidade as capacidade
            LIMIT 1
            """,
            {"id": ativo_id},
        ).single()
        fator_red = redundancia_result["capacidade"] if redundancia_result else 0.0

        p_falha = probabilidade_falha(lambda_max, janela_horas)
        impacto = calcular_impacto(n_downstream)
        escore = calcular_escore(p_falha, impacto, fator_red)

        return EscoreRisco(
            ativo_id=ativo_id,
            escore=escore,
            p_falha=p_falha,
            impacto=impacto,
            fator_redundancia=fator_red,
            lambda_hat=lambda_max,
            janela_horas=janela_horas,
            ic_inferior_lambda=ic_inf_max,
            ic_superior_lambda=ic_sup_max,
            defeitos_abertos=defeitos_ids,
        )
