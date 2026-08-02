from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class LocalizacaoDefeitoParams(BaseModel):
    defeito_id: str


class LocalizacaoDefeito(IntencaoBase):
    """Onde exatamente esta o defeito, dentro do equipamento.

    O grafo separa o equipamento da parte mantida (ParteObjeto), que e o que
    a ISO 14224 chama de item mantido. Sem essa distincao nao se consegue
    dizer que dois defeitos diferentes atingem a mesma peca.
    """

    nome = "localizacao_defeito"
    descricao = (
        "Localiza um defeito na parte especifica do equipamento e mostra "
        "que outros defeitos ja atingiram a mesma parte"
    )

    def executar(self, session, params: LocalizacaoDefeitoParams) -> EnvelopeEvidencia:
        rec = session.run(
            """
            MATCH (d:Defeito {id: $did})
            OPTIONAL MATCH (d)-[:DETECTADO_EM]->(eq:Equipamento)
            OPTIONAL MATCH (d)-[:MANIFESTOU]->(mf:ModoFalha)
            RETURN d, eq, mf
            """,
            parameters={"did": params.defeito_id},
        ).single()
        if rec is None:
            raise KeyError(f"Defeito '{params.defeito_id}' nao encontrado.")

        d, eq, mf = rec["d"], rec.get("eq"), rec.get("mf")

        nos = [NoEvidencia(
            label="Defeito", id=d["id"],
            propriedades={"descricao": d.get("descricao", ""), "status": d.get("status", "")},
        )]
        arestas = []
        ids_vistos = {d["id"]}

        if eq:
            ids_vistos.add(eq["id"])
            nos.append(NoEvidencia(
                label="Equipamento", id=eq["id"],
                propriedades={"descricao": eq.get("descricao", "")},
            ))
            arestas.append(ArestaEvidencia(
                tipo="DETECTADO_EM", origem_id=d["id"], destino_id=eq["id"],
            ))

        if mf:
            ids_vistos.add(mf["id"])
            nos.append(NoEvidencia(
                label="ModoFalha", id=mf["id"],
                propriedades={"descricao": mf.get("descricao", "")},
            ))
            arestas.append(ArestaEvidencia(
                tipo="MANIFESTOU", origem_id=d["id"], destino_id=mf["id"],
            ))

        partes = []
        for r in session.run(
            "MATCH (d:Defeito {id: $did})-[:IDENTIFICADO_EM]->(p:ParteObjeto) RETURN p",
            parameters={"did": params.defeito_id},
        ):
            p = r["p"]
            partes.append(p)
            if p["id"] not in ids_vistos:
                ids_vistos.add(p["id"])
                nos.append(NoEvidencia(
                    label="ParteObjeto", id=p["id"],
                    propriedades={"descricao": p.get("descricao", "")},
                ))
            arestas.append(ArestaEvidencia(
                tipo="IDENTIFICADO_EM", origem_id=d["id"], destino_id=p["id"],
            ))

        # Reincidencia na mesma peca: o argumento de que o problema e cronico
        # so se sustenta se outros defeitos apontarem para a mesma ParteObjeto.
        reincidentes = set()
        for p in partes:
            for r in session.run(
                """
                MATCH (outro:Defeito)-[:IDENTIFICADO_EM]->(p:ParteObjeto {id: $pid})
                WHERE outro.id <> $did
                RETURN outro
                """,
                parameters={"pid": p["id"], "did": params.defeito_id},
            ):
                o = r["outro"]
                reincidentes.add(o["id"])
                if o["id"] not in ids_vistos:
                    ids_vistos.add(o["id"])
                    nos.append(NoEvidencia(
                        label="Defeito", id=o["id"],
                        propriedades={
                            "descricao": o.get("descricao", ""),
                            "status": o.get("status", ""),
                        },
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="IDENTIFICADO_EM", origem_id=o["id"], destino_id=p["id"],
                ))

        calculos = [
            CalculoEvidencia(
                nome="partes_afetadas", formula="count(ParteObjeto)",
                valor=len(partes), unidade="partes",
            ),
            CalculoEvidencia(
                nome="outros_defeitos_na_mesma_parte", formula="count(distinct Defeito) - 1",
                valor=len(reincidentes), unidade="defeitos",
            ),
        ]

        lacunas = []
        if not partes:
            lacunas.append(
                "Defeito sem parte identificada — o modo de falha nao permite "
                "derivar a peca afetada.",
            )

        nome_partes = ", ".join(p.get("descricao", p["id"]) for p in partes) or "parte nao identificada"
        eq_desc = eq.get("descricao", "") if eq else "equipamento desconhecido"
        return EnvelopeEvidencia(
            afirmacao=(
                f"O defeito {params.defeito_id} esta localizado em: {nome_partes}, "
                f"no equipamento {eq_desc}. "
                f"Outros {len(reincidentes)} defeito(s) ja atingiram a mesma parte."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
