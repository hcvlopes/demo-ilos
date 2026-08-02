from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class ListarEquipamentosParams(BaseModel):
    ativo_id: str


class ListarEquipamentosAtivo(IntencaoBase):
    nome = "listar_equipamentos_ativo"
    descricao = "Lista todos os equipamentos de um ativo com classe taxonomica, fabricante e defeitos abertos"

    def executar(self, session, params: ListarEquipamentosParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (eq:Equipamento)-[:PERTENCE]->(a:Ativo {id: $aid})
            OPTIONAL MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (eq)-[:FABRICADO]->(fab:Fabricante)
            OPTIONAL MATCH (d:Defeito {status: 'aberto'})-[:DETECTADO_EM]->(eq)
            RETURN a, eq, ct, fab, count(d) AS defeitos_abertos
            """,
            parameters={"aid": params.ativo_id},
        )

        nos, arestas = [], []
        ids_vistos = set()
        ativo_node = None
        equip_count = 0
        total_defeitos = 0

        for record in result:
            a = record["a"]
            if a and a["id"] not in ids_vistos:
                ids_vistos.add(a["id"])
                ativo_node = a
                nos.append(NoEvidencia(
                    label="Ativo", id=a["id"],
                    propriedades={"descricao": a.get("descricao", "")},
                ))

            eq = record.get("eq")
            if eq and eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                equip_count += 1
                n_def = record.get("defeitos_abertos", 0) or 0
                total_defeitos += n_def
                props = {"descricao": eq.get("descricao", "")}
                if n_def > 0:
                    props["defeitos_abertos"] = n_def
                nos.append(NoEvidencia(label="Equipamento", id=eq["id"], propriedades=props))
                arestas.append(ArestaEvidencia(
                    tipo="PERTENCE", origem_id=eq["id"], destino_id=params.ativo_id,
                ))

                ct = record.get("ct")
                if ct and ct["id"] not in ids_vistos:
                    ids_vistos.add(ct["id"])
                    nos.append(NoEvidencia(
                        label="ClasseTaxonomia", id=ct["id"],
                        propriedades={"descricao": ct.get("descricao", "")},
                    ))
                if ct:
                    arestas.append(ArestaEvidencia(
                        tipo="CLASSIFICADO_COMO", origem_id=eq["id"], destino_id=ct["id"],
                    ))

                fab = record.get("fab")
                if fab and fab["id"] not in ids_vistos:
                    ids_vistos.add(fab["id"])
                    nos.append(NoEvidencia(
                        label="Fabricante", id=fab["id"],
                        propriedades={"nome": fab.get("nome", ""), "pais": fab.get("pais", "")},
                    ))
                if fab:
                    arestas.append(ArestaEvidencia(
                        tipo="FABRICADO", origem_id=eq["id"], destino_id=fab["id"],
                    ))

        if ativo_node is None:
            raise KeyError(f"Ativo '{params.ativo_id}' nao encontrado.")

        lacunas = []
        if equip_count == 0:
            lacunas.append("Nenhum equipamento encontrado para este ativo.")

        calculos = [
            CalculoEvidencia(
                nome="total_equipamentos", formula="count(Equipamento)",
                valor=equip_count, unidade="equipamentos",
            ),
            CalculoEvidencia(
                nome="defeitos_abertos", formula="count(Defeito{status:aberto})",
                valor=total_defeitos, unidade="defeitos",
            ),
        ]

        desc = ativo_node.get("descricao", params.ativo_id)
        return EnvelopeEvidencia(
            afirmacao=f"O ativo {params.ativo_id} ({desc}) possui {equip_count} equipamento(s) "
                      f"com {total_defeitos} defeito(s) aberto(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
