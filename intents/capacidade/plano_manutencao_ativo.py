from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class PlanoManutencaoParams(BaseModel):
    ativo_id: str


class PlanoManutencaoAtivo(IntencaoBase):
    nome = "plano_manutencao_ativo"
    descricao = "Mostra planos de manutencao que cobrem um ativo, com listas de tarefa e ordens geradas"

    def executar(self, session, params: PlanoManutencaoParams) -> EnvelopeEvidencia:
        r_base = session.run(
            "MATCH (a:Ativo {id: $aid}) RETURN a",
            parameters={"aid": params.ativo_id},
        )
        rec = r_base.single()
        if rec is None:
            raise KeyError(f"Ativo '{params.ativo_id}' nao encontrado.")

        ativo_node = rec["a"]
        nos = [NoEvidencia(
            label="Ativo", id=ativo_node["id"],
            propriedades={"descricao": ativo_node.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {params.ativo_id}

        result = session.run(
            """
            MATCH (pm:PlanoManutencao)-[:COBRE]->(a:Ativo {id: $aid})
            OPTIONAL MATCH (pm)-[:USA_LISTA]->(lt:ListaTarefa)
            OPTIONAL MATCH (pm)-[:GEROU_ORDEM]->(om:OrdemManutencao)
            RETURN pm, lt, om
            """,
            parameters={"aid": params.ativo_id},
        )

        planos, listas, ordens = set(), set(), set()
        for record in result:
            pm = record["pm"]
            if pm and pm["id"] not in ids_vistos:
                ids_vistos.add(pm["id"])
                planos.add(pm["id"])
                nos.append(NoEvidencia(
                    label="PlanoManutencao", id=pm["id"],
                    propriedades={"descricao": pm.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="COBRE", origem_id=pm["id"], destino_id=params.ativo_id,
                ))

            lt = record.get("lt")
            if lt and lt["id"] not in ids_vistos:
                ids_vistos.add(lt["id"])
                listas.add(lt["id"])
                nos.append(NoEvidencia(
                    label="ListaTarefa", id=lt["id"],
                    propriedades={"descricao": lt.get("descricao", "")},
                ))
                if pm:
                    arestas.append(ArestaEvidencia(
                        tipo="USA_LISTA", origem_id=pm["id"], destino_id=lt["id"],
                    ))

            om = record.get("om")
            if om and om["id"] not in ids_vistos:
                ids_vistos.add(om["id"])
                ordens.add(om["id"])
                nos.append(NoEvidencia(
                    label="OrdemManutencao", id=om["id"],
                    propriedades={"descricao": om.get("descricao", ""), "tipo": om.get("tipo", "")},
                ))
                if pm:
                    arestas.append(ArestaEvidencia(
                        tipo="GEROU_ORDEM", origem_id=pm["id"], destino_id=om["id"],
                    ))

        calculos = [
            CalculoEvidencia(nome="planos", formula="count(PlanoManutencao)", valor=len(planos), unidade="planos"),
            CalculoEvidencia(nome="listas_tarefa", formula="count(ListaTarefa)", valor=len(listas), unidade="listas"),
            CalculoEvidencia(nome="ordens_geradas", formula="count(OrdemManutencao)", valor=len(ordens), unidade="ordens"),
        ]

        lacunas = []
        if not planos:
            lacunas.append("Nenhum plano de manutencao cobrindo este ativo.")
        if planos and not listas:
            lacunas.append("Plano(s) existente(s) sem lista de tarefa associada.")

        desc = ativo_node.get("descricao", params.ativo_id)
        return EnvelopeEvidencia(
            afirmacao=f"O ativo {params.ativo_id} ({desc}) e coberto por {len(planos)} plano(s) de manutencao "
                      f"com {len(listas)} lista(s) de tarefa e {len(ordens)} ordem(ns) gerada(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
