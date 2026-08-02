from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class DependenciasAtivoParams(BaseModel):
    ativo_id: str


class DependenciasAtivo(IntencaoBase):
    nome = "dependencias_ativo"
    descricao = "Mostra a cadeia de dependencias de um ativo: quem alimenta, quem depende e redundancias"

    def executar(self, session, params: DependenciasAtivoParams) -> EnvelopeEvidencia:
        r_base = session.run(
            "MATCH (a:Ativo {id: $aid}) RETURN a",
            parameters={"aid": params.ativo_id},
        )
        rec = r_base.single()
        if rec is None:
            raise KeyError(f"Ativo '{params.ativo_id}' nao encontrado.")

        a_node = rec["a"]
        nos = [NoEvidencia(
            label="Ativo", id=a_node["id"],
            propriedades={"descricao": a_node.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {params.ativo_id}

        r_down = session.run(
            "MATCH (a:Ativo {id: $aid})-[:ALIMENTA*1..]->(d:Ativo) RETURN d",
            parameters={"aid": params.ativo_id},
        )
        downstream = set()
        for record in r_down:
            d = record["d"]
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                downstream.add(d["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=d["id"],
                    propriedades={"descricao": d.get("descricao", "")},
                ))

        r_up = session.run(
            "MATCH (u:Ativo)-[:ALIMENTA*1..]->(a:Ativo {id: $aid}) RETURN u",
            parameters={"aid": params.ativo_id},
        )
        upstream = set()
        for record in r_up:
            u = record["u"]
            if u and u["id"] not in ids_vistos:
                ids_vistos.add(u["id"])
                upstream.add(u["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=u["id"],
                    propriedades={"descricao": u.get("descricao", "")},
                ))

        r_edges = session.run(
            """
            MATCH (a:Ativo)-[r:ALIMENTA]->(b:Ativo)
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN a.id AS origem, b.id AS destino
            """,
            parameters={"ids": list(ids_vistos)},
        )
        for record in r_edges:
            arestas.append(ArestaEvidencia(
                tipo="ALIMENTA", origem_id=record["origem"], destino_id=record["destino"],
            ))

        r_red = session.run(
            """
            MATCH (a:Ativo {id: $aid})-[r:REDUNDA_COM]->(red:Ativo)
            RETURN red, r.capacidade AS capacidade
            """,
            parameters={"aid": params.ativo_id},
        )
        redundancias = []
        for record in r_red:
            red = record["red"]
            cap = record.get("capacidade", 0)
            redundancias.append((red["id"], cap))
            if red["id"] not in ids_vistos:
                ids_vistos.add(red["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=red["id"],
                    propriedades={"descricao": red.get("descricao", "")},
                ))
            arestas.append(ArestaEvidencia(
                tipo="REDUNDA_COM", origem_id=params.ativo_id, destino_id=red["id"],
                propriedades={"capacidade": cap},
            ))

        calculos = [
            CalculoEvidencia(nome="upstream", formula="count(ALIMENTA*..->ativo)", valor=len(upstream), unidade="ativos"),
            CalculoEvidencia(nome="downstream", formula="count(ativo->ALIMENTA*..)", valor=len(downstream), unidade="ativos"),
            CalculoEvidencia(nome="redundancias", formula="count(REDUNDA_COM)", valor=len(redundancias), unidade="ativos"),
        ]

        lacunas = []
        if not upstream and not downstream:
            lacunas.append("Ativo isolado: sem dependencias de alimentacao.")
        if not redundancias:
            lacunas.append("Nenhuma redundancia configurada para este ativo.")

        return EnvelopeEvidencia(
            afirmacao=f"O ativo {params.ativo_id} recebe de {len(upstream)} ativo(s), "
                      f"alimenta {len(downstream)} ativo(s) e possui {len(redundancias)} redundancia(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
