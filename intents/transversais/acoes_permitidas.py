"""Intencao: acoes_permitidas (F8 — versao completa).

Dado um defeito_id, retorna as acoes permitidas para o modo de falha
na classe taxonomica do equipamento, ordenadas por viabilidade,
com papel autorizador para cada acao.
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


class AcoesPermitidasParams(BaseModel):
    defeito_id: str


class AcoesPermitidas(IntencaoBase):
    nome = "acoes_permitidas"
    descricao = "Acoes permitidas para um defeito, ordenadas por viabilidade, com papel autorizador"

    def executar(self, session, params: AcoesPermitidasParams) -> EnvelopeEvidencia:
        base = session.run(
            """
            MATCH (df:Defeito {id: $id})-[:DETECTADO_EM]->(eq:Equipamento)
                  -[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (df)-[:MANIFESTOU]->(mf:ModoFalha)
            OPTIONAL MATCH (ct)-[:REGULADO_POR]->(n:Norma)
            RETURN df, eq, ct, mf, n
            """,
            {"id": params.defeito_id},
        ).single()

        if base is None:
            return EnvelopeEvidencia(
                afirmacao=f"Defeito {params.defeito_id} nao encontrado.",
                nos=[],
                arestas=[],
                calculos=[],
                normas=[],
                lacunas=[f"Defeito {params.defeito_id} inexistente"],
            )

        df = base["df"]
        eq = base["eq"]
        ct = base["ct"]
        mf = base["mf"]
        norma = base["n"]

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

        normas = []
        if norma is not None:
            nos.append(NoEvidencia(label="Norma", id=norma["id"], propriedades=dict(norma)))
            arestas.append(ArestaEvidencia(tipo="REGULADO_POR", origem_id=ct["id"], destino_id=norma["id"]))
            normas.append(NormaEvidencia(codigo=norma.get("codigo", norma["id"]), descricao=norma.get("descricao", "")))

        acoes_result = session.run(
            """
            MATCH (ct:ClasseTaxonomia {id: $ct_id})-[r:PERMITE]->(ap:AcaoPermitida)
                  -[:APLICAVEL_MODO]->(mf:ModoFalha {id: $mf_id})
            OPTIONAL MATCH (p:Papel)-[:AUTORIZA]->(ap)
            RETURN ap, r.viabilidade as viabilidade, collect(DISTINCT p) as papeis
            ORDER BY r.viabilidade DESC
            """,
            {"ct_id": ct["id"], "mf_id": mf["id"] if mf else "__none__"},
        )

        n_acoes = 0
        calculos = []
        for record in acoes_result:
            ap = record["ap"]
            viab = record["viabilidade"]
            papeis = record["papeis"]
            n_acoes += 1

            nos.append(NoEvidencia(label="AcaoPermitida", id=ap["id"], propriedades=dict(ap)))
            arestas.append(ArestaEvidencia(
                tipo="PERMITE", origem_id=ct["id"], destino_id=ap["id"],
                propriedades={"viabilidade": viab},
            ))
            if mf is not None:
                arestas.append(ArestaEvidencia(tipo="APLICAVEL_MODO", origem_id=ap["id"], destino_id=mf["id"]))

            for p in papeis:
                if p is not None:
                    no_p = NoEvidencia(label="Papel", id=p["id"], propriedades=dict(p))
                    if no_p not in nos:
                        nos.append(no_p)
                    arestas.append(ArestaEvidencia(tipo="AUTORIZA", origem_id=p["id"], destino_id=ap["id"]))

            calculos.append(CalculoEvidencia(
                nome=f"viabilidade_{ap['id']}",
                formula="viabilidade(complexidade)",
                valor=viab,
                unidade="adimensional",
            ))

        # Fallback: historical actions if no catalog match
        if n_acoes == 0 and mf is not None:
            hist_result = session.run(
                """
                MATCH (ef:EventoFalha)-[:MANIFESTOU]->(mf:ModoFalha {id: $mf_id})
                MATCH (ef)-[:OCORREU]->(eq2:Equipamento)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia {id: $ct_id})
                MATCH (om:OrdemManutencao)-[:RESOLVE]->(ef)
                RETURN DISTINCT om, ef
                LIMIT 10
                """,
                {"mf_id": mf["id"], "ct_id": ct["id"]},
            )
            for record in hist_result:
                om = record["om"]
                ef = record["ef"]
                n_acoes += 1
                nos.append(NoEvidencia(label="OrdemManutencao", id=om["id"], propriedades=dict(om)))
                nos.append(NoEvidencia(label="EventoFalha", id=ef["id"], propriedades=dict(ef)))
                arestas.append(ArestaEvidencia(tipo="RESOLVE", origem_id=om["id"], destino_id=ef["id"]))

        lacunas = []
        if mf is None:
            lacunas.append("Modo de falha nao registrado — busca por catalogo impossivel")
        if n_acoes == 0:
            lacunas.append("Nenhuma acao permitida ou historica encontrada para este modo de falha")

        modo_desc = mf["descricao"] if mf else "desconhecido"
        afirmacao = (
            f"Defeito {df['id']}: {n_acoes} acao(oes) permitida(s) "
            f"para modo '{modo_desc}' na classe {ct['id']}, "
            f"ordenadas por viabilidade."
        )

        return EnvelopeEvidencia(
            afirmacao=afirmacao,
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=normas,
            lacunas=lacunas,
        )
