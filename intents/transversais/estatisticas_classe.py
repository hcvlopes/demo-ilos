from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)


class EstatisticasClasseParams(BaseModel):
    classe_id: str


class EstatisticasClasse(IntencaoBase):
    nome = "estatisticas_classe"
    descricao = "Mostra estatisticas de confiabilidade de uma classe taxonomica: lambda, IC, equipamentos e defeitos"

    def executar(self, session, params: EstatisticasClasseParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (ct:ClasseTaxonomia {id: $cid})
            OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
            OPTIONAL MATCH (eq:Equipamento)-[:CLASSIFICADO_COMO]->(ct)
            OPTIONAL MATCH (ct)-[:REGULADO_POR]->(n:Norma)
            RETURN ct, mc, collect(DISTINCT eq) AS equipamentos, n
            """,
            parameters={"cid": params.classe_id},
        )

        nos, arestas, calculos = [], [], []
        ids_vistos = set()
        ct_node = None
        normas_ev = []
        equip_count = 0

        for record in result:
            ct = record["ct"]
            if ct and ct["id"] not in ids_vistos:
                ids_vistos.add(ct["id"])
                ct_node = ct
                props = {"descricao": ct.get("descricao", "")}
                lref = ct.get("lambda_ref_1e6h")
                if lref is not None:
                    props["lambda_ref_1e6h"] = lref
                nos.append(NoEvidencia(label="ClasseTaxonomia", id=ct["id"], propriedades=props))

            mc = record.get("mc")
            if mc and mc["id"] not in ids_vistos:
                ids_vistos.add(mc["id"])
                nos.append(NoEvidencia(
                    label="MetricaConfiabilidade", id=mc["id"],
                    propriedades={
                        "lambda_hat": mc.get("lambda_hat", ""),
                        "n_eventos": mc.get("n_eventos", ""),
                        "horas_operacao": mc.get("horas_operacao", ""),
                        "metodo": mc.get("metodo", ""),
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="TEM_METRICA", origem_id=params.classe_id, destino_id=mc["id"],
                ))
                lh = mc.get("lambda_hat")
                if lh is not None:
                    calculos.append(CalculoEvidencia(
                        nome="lambda_hat",
                        formula="n_eventos / horas_operacao",
                        valor=float(lh),
                        unidade="falhas/h_op",
                        ic_inferior=mc.get("ic_inferior"),
                        ic_superior=mc.get("ic_superior"),
                    ))
                ne = mc.get("n_eventos")
                ho = mc.get("horas_operacao")
                if ne is not None:
                    calculos.append(CalculoEvidencia(
                        nome="n_eventos", formula="count(EventoFalha)",
                        valor=int(ne), unidade="eventos",
                    ))
                if ho is not None:
                    calculos.append(CalculoEvidencia(
                        nome="horas_operacao", formula="sum(horas)",
                        valor=float(ho), unidade="horas",
                    ))

            eqs = record.get("equipamentos")
            if eqs:
                for eq in eqs:
                    if eq and eq["id"] not in ids_vistos:
                        ids_vistos.add(eq["id"])
                        equip_count += 1
                        nos.append(NoEvidencia(
                            label="Equipamento", id=eq["id"],
                            propriedades={"descricao": eq.get("descricao", "")},
                        ))
                        arestas.append(ArestaEvidencia(
                            tipo="CLASSIFICADO_COMO", origem_id=eq["id"], destino_id=params.classe_id,
                        ))

            n = record.get("n")
            if n and n["id"] not in ids_vistos:
                ids_vistos.add(n["id"])
                nos.append(NoEvidencia(
                    label="Norma", id=n["id"],
                    propriedades={"codigo": n.get("codigo", ""), "descricao": n.get("descricao", "")},
                ))
                normas_ev.append(NormaEvidencia(
                    codigo=n.get("codigo", n["id"]),
                    descricao=n.get("descricao", ""),
                ))
                arestas.append(ArestaEvidencia(
                    tipo="REGULADO_POR", origem_id=params.classe_id, destino_id=n["id"],
                ))

        if ct_node is None:
            raise KeyError(f"Classe taxonomica '{params.classe_id}' nao encontrada.")

        calculos.append(CalculoEvidencia(
            nome="equipamentos_na_classe", formula="count(Equipamento)",
            valor=equip_count, unidade="equipamentos",
        ))

        lacunas = []
        if not any(c.nome == "lambda_hat" for c in calculos):
            lacunas.append("Nenhuma metrica de confiabilidade disponivel para esta classe.")

        desc = ct_node.get("descricao", params.classe_id)
        return EnvelopeEvidencia(
            afirmacao=f"A classe {params.classe_id} ({desc}) possui {equip_count} equipamento(s) classificado(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=normas_ev,
            lacunas=lacunas,
        )
