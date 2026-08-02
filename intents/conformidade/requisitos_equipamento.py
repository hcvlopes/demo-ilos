from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)


class RequisitosEquipamentoParams(BaseModel):
    equipamento_id: str


class RequisitosEquipamento(IntencaoBase):
    """A visao inversa da conformidade: o que incide sobre este equipamento.

    Responde de onde vem cada exigencia — regulacao direta do equipamento ou
    heranca da classe taxonomica. A procedencia importa: sem ela a resposta
    vira uma lista de requisitos sem quem os justifique.
    """

    nome = "requisitos_equipamento"
    descricao = (
        "Lista os requisitos normativos que incidem sobre um equipamento, "
        "indicando se vem de regulacao direta ou da classe taxonomica"
    )

    def executar(self, session, params: RequisitosEquipamentoParams) -> EnvelopeEvidencia:
        rec = session.run(
            "MATCH (eq:Equipamento {id: $eid}) RETURN eq",
            parameters={"eid": params.equipamento_id},
        ).single()
        if rec is None:
            raise KeyError(f"Equipamento '{params.equipamento_id}' nao encontrado.")

        eq = rec["eq"]
        nos = [NoEvidencia(
            label="Equipamento", id=eq["id"],
            propriedades={"descricao": eq.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {eq["id"]}
        normas_ev = []
        requisitos_por_via = {"direta": set(), "classe": set()}
        criticos = set()

        def registrar_norma(n, origem_id, via_label):
            if n["id"] not in ids_vistos:
                ids_vistos.add(n["id"])
                nos.append(NoEvidencia(
                    label="Norma", id=n["id"],
                    propriedades={"codigo": n.get("codigo", ""), "descricao": n.get("descricao", "")},
                ))
                normas_ev.append(NormaEvidencia(
                    codigo=n.get("codigo", n["id"]), descricao=n.get("descricao", ""),
                ))
            arestas.append(ArestaEvidencia(
                tipo="REGULADO_POR", origem_id=origem_id, destino_id=n["id"],
                propriedades={"via": via_label},
            ))

        def registrar_requisitos(norma_id, via):
            for r in session.run(
                "MATCH (n:Norma {id: $nid})-[:TEM_REQUISITO]->(rq:Requisito) "
                "RETURN rq ORDER BY rq.id",
                parameters={"nid": norma_id},
            ):
                rq = r["rq"]
                requisitos_por_via[via].add(rq["id"])
                if rq.get("criticidade") == "alta":
                    criticos.add(rq["id"])
                if rq["id"] not in ids_vistos:
                    ids_vistos.add(rq["id"])
                    nos.append(NoEvidencia(
                        label="Requisito", id=rq["id"],
                        propriedades={
                            "descricao": rq.get("descricao", ""),
                            "criticidade": rq.get("criticidade", ""),
                        },
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="TEM_REQUISITO", origem_id=norma_id, destino_id=rq["id"],
                ))

        for r in session.run(
            "MATCH (eq:Equipamento {id: $eid})-[:REGULADO_POR]->(n:Norma) RETURN n",
            parameters={"eid": params.equipamento_id},
        ):
            registrar_norma(r["n"], params.equipamento_id, "direta")
            registrar_requisitos(r["n"]["id"], "direta")

        for r in session.run(
            """
            MATCH (eq:Equipamento {id: $eid})-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
                  -[:REGULADO_POR]->(n:Norma)
            RETURN ct, n
            """,
            parameters={"eid": params.equipamento_id},
        ):
            ct, n = r["ct"], r["n"]
            if ct["id"] not in ids_vistos:
                ids_vistos.add(ct["id"])
                nos.append(NoEvidencia(
                    label="ClasseTaxonomia", id=ct["id"],
                    propriedades={"descricao": ct.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="CLASSIFICADO_COMO",
                    origem_id=params.equipamento_id, destino_id=ct["id"],
                ))
            registrar_norma(n, ct["id"], "classe")
            registrar_requisitos(n["id"], "classe")

        todos = requisitos_por_via["direta"] | requisitos_por_via["classe"]

        calculos = [
            CalculoEvidencia(
                nome="requisitos_aplicaveis", formula="count(distinct Requisito)",
                valor=len(todos), unidade="requisitos",
            ),
            CalculoEvidencia(
                nome="por_regulacao_direta", formula="count(Requisito via Equipamento-REGULADO_POR)",
                valor=len(requisitos_por_via["direta"]), unidade="requisitos",
            ),
            CalculoEvidencia(
                nome="por_classe_taxonomica",
                formula="count(Requisito via ClasseTaxonomia-REGULADO_POR)",
                valor=len(requisitos_por_via["classe"]), unidade="requisitos",
            ),
            CalculoEvidencia(
                nome="criticidade_alta", formula="count(Requisito onde criticidade=alta)",
                valor=len(criticos), unidade="requisitos",
            ),
        ]

        lacunas = []
        if not todos:
            lacunas.append("Nenhuma norma declarada para este equipamento nem para sua classe.")
        if requisitos_por_via["classe"] and not requisitos_por_via["direta"]:
            lacunas.append(
                "Exigencias vem apenas da classe taxonomica — "
                "nenhuma norma foi declarada diretamente neste equipamento.",
            )

        desc = eq.get("descricao", params.equipamento_id)
        return EnvelopeEvidencia(
            afirmacao=(
                f"Sobre o equipamento {params.equipamento_id} ({desc}) incidem "
                f"{len(todos)} requisito(s) normativo(s), {len(criticos)} de criticidade alta, "
                f"vindos de {len(normas_ev)} norma(s)."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=normas_ev,
            lacunas=lacunas,
        )
