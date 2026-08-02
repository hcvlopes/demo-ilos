from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class OrdensManutencaoParams(BaseModel):
    equipamento_id: str


class OrdensManutencao(IntencaoBase):
    nome = "ordens_manutencao"
    descricao = "Lista ordens de manutencao de um equipamento com etapas, equipes e materiais usados"

    def executar(self, session, params: OrdensManutencaoParams) -> EnvelopeEvidencia:
        r_eq = session.run(
            "MATCH (eq:Equipamento {id: $eid}) RETURN eq",
            parameters={"eid": params.equipamento_id},
        )
        rec = r_eq.single()
        if rec is None:
            raise KeyError(f"Equipamento '{params.equipamento_id}' nao encontrado.")

        eq_node = rec["eq"]
        nos = [NoEvidencia(
            label="Equipamento", id=eq_node["id"],
            propriedades={"descricao": eq_node.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {params.equipamento_id}

        result = session.run(
            """
            MATCH (om:OrdemManutencao)-[:EXECUTADA_EM]->(eq:Equipamento {id: $eid})
            OPTIONAL MATCH (om)-[:TEM_ETAPA]->(et:Etapa)
            OPTIONAL MATCH (et)-[:EXECUTADA_POR]->(equipe:Equipe)
            OPTIONAL MATCH (et)-[:USA_MATERIAL]->(mat:Material)
            OPTIONAL MATCH (om)-[:RESOLVE]->(d:Defeito)
            RETURN om, et, equipe, mat, d
            """,
            parameters={"eid": params.equipamento_id},
        )

        ordens = set()
        for record in result:
            om = record["om"]
            if om and om["id"] not in ids_vistos:
                ids_vistos.add(om["id"])
                ordens.add(om["id"])
                nos.append(NoEvidencia(
                    label="OrdemManutencao", id=om["id"],
                    propriedades={
                        "descricao": om.get("descricao", ""),
                        "tipo": om.get("tipo", ""),
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="EXECUTADA_EM", origem_id=om["id"], destino_id=params.equipamento_id,
                ))

            et = record.get("et")
            if et and et["id"] not in ids_vistos:
                ids_vistos.add(et["id"])
                nos.append(NoEvidencia(
                    label="Etapa", id=et["id"],
                    propriedades={"descricao": et.get("descricao", "")},
                ))
                if om:
                    arestas.append(ArestaEvidencia(
                        tipo="TEM_ETAPA", origem_id=om["id"], destino_id=et["id"],
                    ))

            equipe = record.get("equipe")
            if equipe and equipe["id"] not in ids_vistos:
                ids_vistos.add(equipe["id"])
                nos.append(NoEvidencia(
                    label="Equipe", id=equipe["id"],
                    propriedades={"descricao": equipe.get("descricao", "")},
                ))

            d = record.get("d")
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={"descricao": d.get("descricao", ""), "status": d.get("status", "")},
                ))
                if om:
                    arestas.append(ArestaEvidencia(
                        tipo="RESOLVE", origem_id=om["id"], destino_id=d["id"],
                    ))

        calculos = [
            CalculoEvidencia(
                nome="total_ordens", formula="count(OrdemManutencao)",
                valor=len(ordens), unidade="ordens",
            ),
        ]

        lacunas = []
        if not ordens:
            lacunas.append("Nenhuma ordem de manutencao encontrada para este equipamento.")

        desc = eq_node.get("descricao", params.equipamento_id)
        return EnvelopeEvidencia(
            afirmacao=f"O equipamento {params.equipamento_id} ({desc}) possui {len(ordens)} ordem(ns) de manutencao.",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
