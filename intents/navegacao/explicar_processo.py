from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)


class ExplicarProcessoParams(BaseModel):
    processo_id: str


class ExplicarProcesso(IntencaoBase):
    nome = "explicar_processo"
    descricao = "Explica um processo operacional: funcoes requeridas, ativos envolvidos, entregas, contratos e indicadores"

    def executar(self, session, params: ExplicarProcessoParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (p:ProcessoOperacional {id: $pid})
            OPTIONAL MATCH (p)-[:REQUER]->(f:Funcao)
            OPTIONAL MATCH (f)<-[:DESEMPENHA]-(a:Ativo)
            OPTIONAL MATCH (e:Entrega)-[:VINCULADA]->(p)
            OPTIONAL MATCH (c:Contrato)-[:TEM_ENTREGA]->(e)
            OPTIONAL MATCH (i:Indicador)-[:MEDE]->(p)
            RETURN p, f, a, e, c, i
            """,
            parameters={"pid": params.processo_id},
        )

        nos, arestas = [], []
        processo_node = None
        funcoes, ativos, entregas, contratos, indicadores = set(), set(), set(), set(), set()
        ids_vistos = set()

        for record in result:
            p = record["p"]
            if p and p["id"] not in ids_vistos:
                ids_vistos.add(p["id"])
                processo_node = p
                nos.append(NoEvidencia(
                    label="ProcessoOperacional", id=p["id"],
                    propriedades={"descricao": p.get("descricao", "")},
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
                    tipo="REQUER", origem_id=params.processo_id, destino_id=f["id"],
                ))

            a = record.get("a")
            if a and a["id"] not in ids_vistos:
                ids_vistos.add(a["id"])
                ativos.add(a["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=a["id"],
                    propriedades={"descricao": a.get("descricao", "")},
                ))
                if f:
                    arestas.append(ArestaEvidencia(
                        tipo="DESEMPENHA", origem_id=a["id"], destino_id=f["id"],
                    ))

            e = record.get("e")
            if e and e["id"] not in ids_vistos:
                ids_vistos.add(e["id"])
                entregas.add(e["id"])
                nos.append(NoEvidencia(
                    label="Entrega", id=e["id"],
                    propriedades={"descricao": e.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="VINCULADA", origem_id=e["id"], destino_id=params.processo_id,
                ))

            c = record.get("c")
            if c and c["id"] not in ids_vistos:
                ids_vistos.add(c["id"])
                contratos.add(c["id"])
                nos.append(NoEvidencia(
                    label="Contrato", id=c["id"],
                    propriedades={"descricao": c.get("descricao", "")},
                ))
                if e:
                    arestas.append(ArestaEvidencia(
                        tipo="TEM_ENTREGA", origem_id=c["id"], destino_id=e["id"],
                    ))

            i = record.get("i")
            if i and i["id"] not in ids_vistos:
                ids_vistos.add(i["id"])
                indicadores.add(i["id"])
                nos.append(NoEvidencia(
                    label="Indicador", id=i["id"],
                    propriedades={"descricao": i.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="MEDE", origem_id=i["id"], destino_id=params.processo_id,
                ))

        if processo_node is None:
            raise KeyError(f"Processo '{params.processo_id}' nao encontrado.")

        lacunas = []
        if not funcoes:
            lacunas.append("Nenhuma funcao requerida encontrada para este processo.")
        if not ativos:
            lacunas.append("Nenhum ativo desempenhando funcoes deste processo.")
        if not entregas:
            lacunas.append("Nenhuma entrega vinculada ao processo.")
        if not indicadores:
            lacunas.append("Nenhum indicador medindo este processo.")

        calculos = [
            CalculoEvidencia(
                nome="funcoes_requeridas", formula="count(Funcao)",
                valor=len(funcoes), unidade="funcoes",
            ),
            CalculoEvidencia(
                nome="ativos_envolvidos", formula="count(Ativo)",
                valor=len(ativos), unidade="ativos",
            ),
        ]

        desc = processo_node.get("descricao", params.processo_id)
        return EnvelopeEvidencia(
            afirmacao=f"O processo {params.processo_id} ({desc}) requer {len(funcoes)} funcao(oes) "
                      f"desempenhada(s) por {len(ativos)} ativo(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
