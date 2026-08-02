from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)


class NormasAplicaveisParams(BaseModel):
    equipamento_id: str


class NormasAplicaveis(IntencaoBase):
    nome = "normas_aplicaveis"
    descricao = "Lista normas e requisitos aplicaveis a um equipamento, tanto diretas quanto via classe taxonomica"

    def executar(self, session, params: NormasAplicaveisParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (eq:Equipamento {id: $eid})
            OPTIONAL MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (eq)-[:REGULADO_POR]->(n1:Norma)
            OPTIONAL MATCH (ct)-[:REGULADO_POR]->(n2:Norma)
            OPTIONAL MATCH (n1)-[:TEM_REQUISITO]->(r1:Requisito)
            OPTIONAL MATCH (n2)-[:TEM_REQUISITO]->(r2:Requisito)
            RETURN eq, ct, n1, n2, r1, r2
            """,
            parameters={"eid": params.equipamento_id},
        )

        nos, arestas, normas_ev = [], [], []
        ids_vistos = set()
        eq_node = None
        normas_ids = set()

        for record in result:
            eq = record["eq"]
            if eq and eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                eq_node = eq
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))

            ct = record.get("ct")
            if ct and ct["id"] not in ids_vistos:
                ids_vistos.add(ct["id"])
                nos.append(NoEvidencia(
                    label="ClasseTaxonomia", id=ct["id"],
                    propriedades={"descricao": ct.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="CLASSIFICADO_COMO", origem_id=params.equipamento_id, destino_id=ct["id"],
                ))

            for n_key, origem in [("n1", params.equipamento_id), ("n2", ct["id"] if ct else None)]:
                n = record.get(n_key)
                if n and n["id"] not in ids_vistos:
                    ids_vistos.add(n["id"])
                    normas_ids.add(n["id"])
                    nos.append(NoEvidencia(
                        label="Norma", id=n["id"],
                        propriedades={
                            "codigo": n.get("codigo", n["id"]),
                            "descricao": n.get("descricao", ""),
                        },
                    ))
                    normas_ev.append(NormaEvidencia(
                        codigo=n.get("codigo", n["id"]),
                        descricao=n.get("descricao", ""),
                    ))
                    if origem:
                        arestas.append(ArestaEvidencia(
                            tipo="REGULADO_POR", origem_id=origem, destino_id=n["id"],
                        ))

            for r_key, n_key in [("r1", "n1"), ("r2", "n2")]:
                r = record.get(r_key)
                n = record.get(n_key)
                if r and r["id"] not in ids_vistos:
                    ids_vistos.add(r["id"])
                    nos.append(NoEvidencia(
                        label="Requisito", id=r["id"],
                        propriedades={"descricao": r.get("descricao", "")},
                    ))
                    if n:
                        arestas.append(ArestaEvidencia(
                            tipo="TEM_REQUISITO", origem_id=n["id"], destino_id=r["id"],
                        ))

        if eq_node is None:
            raise KeyError(f"Equipamento '{params.equipamento_id}' nao encontrado.")

        lacunas = []
        if not normas_ids:
            lacunas.append("Nenhuma norma aplicavel encontrada para este equipamento ou sua classe.")

        desc = eq_node.get("descricao", params.equipamento_id)
        return EnvelopeEvidencia(
            afirmacao=f"O equipamento {params.equipamento_id} ({desc}) e regulado por {len(normas_ids)} norma(s).",
            nos=nos,
            arestas=arestas,
            calculos=[],
            normas=normas_ev,
            lacunas=lacunas,
        )
