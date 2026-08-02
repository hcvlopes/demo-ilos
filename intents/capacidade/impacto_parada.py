import math

from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class ImpactoParadaParams(BaseModel):
    ativo_id: str


class ImpactoParada(IntencaoBase):
    nome = "impacto_parada"
    descricao = "Analisa o impacto de parada de um ativo: processos afetados, ativos downstream e redundancias disponiveis"

    def executar(self, session, params: ImpactoParadaParams) -> EnvelopeEvidencia:
        r_base = session.run(
            """
            MATCH (a:Ativo {id: $aid})
            OPTIONAL MATCH (a)-[:DESEMPENHA]->(f:Funcao)
            OPTIONAL MATCH (f)<-[:REQUER]-(p:ProcessoOperacional)
            RETURN a, f, p
            """,
            parameters={"aid": params.ativo_id},
        )

        nos, arestas = [], []
        ids_vistos = set()
        ativo_node = None
        funcoes, processos = set(), set()

        for record in r_base:
            a = record["a"]
            if a and a["id"] not in ids_vistos:
                ids_vistos.add(a["id"])
                ativo_node = a
                nos.append(NoEvidencia(
                    label="Ativo", id=a["id"],
                    propriedades={"descricao": a.get("descricao", "")},
                ))

            f = record.get("f")
            if f and f["id"] not in ids_vistos:
                ids_vistos.add(f["id"])
                funcoes.add(f["id"])
                nos.append(NoEvidencia(
                    label="Funcao", id=f["id"],
                    propriedades={"descricao": f.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="DESEMPENHA", origem_id=params.ativo_id, destino_id=f["id"],
                ))

            p = record.get("p")
            if p and p["id"] not in ids_vistos:
                ids_vistos.add(p["id"])
                processos.add(p["id"])
                nos.append(NoEvidencia(
                    label="ProcessoOperacional", id=p["id"],
                    propriedades={"descricao": p.get("descricao", "")},
                ))
                if f:
                    arestas.append(ArestaEvidencia(
                        tipo="REQUER", origem_id=p["id"], destino_id=f["id"],
                    ))

        if ativo_node is None:
            raise KeyError(f"Ativo '{params.ativo_id}' nao encontrado.")

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
                arestas.append(ArestaEvidencia(
                    tipo="ALIMENTA", origem_id=params.ativo_id, destino_id=d["id"],
                ))

        r_red = session.run(
            """
            MATCH (a:Ativo {id: $aid})-[r:REDUNDA_COM]->(red:Ativo)
            RETURN red, r.capacidade AS capacidade
            """,
            parameters={"aid": params.ativo_id},
        )
        redundancias = []
        fator_red_total = 0.0
        for record in r_red:
            red = record["red"]
            cap = record.get("capacidade", 0) or 0
            redundancias.append(red["id"])
            fator_red_total = min(1.0, fator_red_total + float(cap))
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

        impacto_bruto = 1 + len(downstream)
        impacto_liquido = impacto_bruto * (1 - fator_red_total)

        calculos = [
            CalculoEvidencia(
                nome="processos_afetados", formula="count(ProcessoOperacional)",
                valor=len(processos), unidade="processos",
            ),
            CalculoEvidencia(
                nome="ativos_downstream", formula="count(ALIMENTA*..)",
                valor=len(downstream), unidade="ativos",
            ),
            CalculoEvidencia(
                nome="fator_redundancia", formula="sum(capacidade REDUNDA_COM)",
                valor=fator_red_total, unidade="fator 0-1",
            ),
            CalculoEvidencia(
                nome="impacto_bruto", formula="1 + downstream",
                valor=impacto_bruto, unidade="ativos afetados",
            ),
            CalculoEvidencia(
                nome="impacto_liquido", formula="impacto_bruto * (1 - redundancia)",
                valor=round(impacto_liquido, 4), unidade="ativos equivalentes",
            ),
        ]

        lacunas = []
        if not processos:
            lacunas.append("Ativo nao vinculado a nenhum processo operacional.")
        if not redundancias:
            lacunas.append("Nenhuma redundancia disponivel — parada afeta integralmente os downstream.")

        desc = ativo_node.get("descricao", params.ativo_id)
        return EnvelopeEvidencia(
            afirmacao=f"A parada do ativo {params.ativo_id} ({desc}) afeta {len(processos)} processo(s) e "
                      f"{len(downstream)} ativo(s) downstream. "
                      f"Impacto liquido: {round(impacto_liquido, 2)} (redundancia: {round(fator_red_total*100)}%).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
