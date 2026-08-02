"""Intenção: explicar_defeito.

Dado um defeito_id, percorre o grafo para devolver modo, causa, mecanismo,
λ com IC e norma aplicável.
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


class ExplicarDefeitoParams(BaseModel):
    defeito_id: str


class ExplicarDefeito(IntencaoBase):
    nome = "explicar_defeito"
    descricao = "Explica um defeito: modo, causa, mecanismo, lambda com IC e norma"

    def executar(self, session, params: ExplicarDefeitoParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (df:Defeito {id: $id})-[:DETECTADO_EM]->(eq:Equipamento)
                  -[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (df)-[:MANIFESTOU]->(mf:ModoFalha)
            OPTIONAL MATCH (df)-[:CAUSADO_POR]->(cf:CausaFalha)
            OPTIONAL MATCH (df)-[:VIA_MECANISMO]->(mec:MecanismoFalha)
            OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
            OPTIONAL MATCH (ct)-[:REGULADO_POR]->(n:Norma)
            RETURN df, eq, ct, mf, cf, mec, mc, n
            """,
            {"id": params.defeito_id},
        ).single()

        if result is None:
            return EnvelopeEvidencia(
                afirmacao=f"Defeito {params.defeito_id} nao encontrado no grafo.",
                nos=[],
                arestas=[],
                calculos=[],
                normas=[],
                lacunas=[f"Defeito {params.defeito_id} inexistente"],
            )

        df = result["df"]
        eq = result["eq"]
        ct = result["ct"]
        mf = result["mf"]
        cf = result["cf"]
        mec = result["mec"]
        mc = result["mc"]
        norma = result["n"]

        nos = [
            NoEvidencia(label="Defeito", id=df["id"], propriedades=dict(df)),
            NoEvidencia(label="Equipamento", id=eq["id"], propriedades=dict(eq)),
            NoEvidencia(label="ClasseTaxonomia", id=ct["id"], propriedades=dict(ct)),
        ]
        arestas = [
            ArestaEvidencia(tipo="DETECTADO_EM", origem_id=df["id"], destino_id=eq["id"]),
            ArestaEvidencia(tipo="CLASSIFICADO_COMO", origem_id=eq["id"], destino_id=ct["id"]),
        ]

        if mf is not None:
            nos.append(NoEvidencia(label="ModoFalha", id=mf["id"], propriedades=dict(mf)))
            arestas.append(ArestaEvidencia(tipo="MANIFESTOU", origem_id=df["id"], destino_id=mf["id"]))

        if cf is not None:
            nos.append(NoEvidencia(label="CausaFalha", id=cf["id"], propriedades=dict(cf)))
            arestas.append(ArestaEvidencia(tipo="CAUSADO_POR", origem_id=df["id"], destino_id=cf["id"]))

        if mec is not None:
            nos.append(NoEvidencia(label="MecanismoFalha", id=mec["id"], propriedades=dict(mec)))
            arestas.append(ArestaEvidencia(tipo="VIA_MECANISMO", origem_id=df["id"], destino_id=mec["id"]))

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
        if mf is None:
            lacunas.append("Modo de falha nao registrado")
        if cf is None:
            lacunas.append("Causa de falha nao registrada")
        if mec is None:
            lacunas.append("Mecanismo de falha nao registrado")
        if mc is None:
            lacunas.append("Metrica de confiabilidade nao calculada para esta classe")

        modo_desc = mf["descricao"] if mf else "desconhecido"
        causa_desc = cf["descricao"] if cf else "desconhecida"
        mec_desc = mec["descricao"] if mec else "desconhecido"

        afirmacao = (
            f"Defeito {df['id']} no equipamento {eq['id']} ({ct['descricao']}): "
            f"modo {modo_desc}, causa {causa_desc}, mecanismo {mec_desc}."
        )
        if mc is not None:
            afirmacao += (
                f" Taxa de falha estimada: {mc['lambda_hat']:.6f} falhas/hora "
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
