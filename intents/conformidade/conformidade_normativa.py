from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
    contar,
)


class ConformidadeNormativaParams(BaseModel):
    norma_id: str


class ConformidadeNormativa(IntencaoBase):
    """Dada uma norma, o que ela exige e a quem se aplica.

    E a pergunta que sustenta a tese do projeto: o alcance de uma norma so e
    respondivel se o grafo declarar a regulacao. Um dashboard de manutencao
    nao sabe dizer quais equipamentos estao sujeitos a NR-12, porque a
    relacao equipamento-norma nao esta em lugar nenhum dele.
    """

    nome = "conformidade_normativa"
    descricao = (
        "Mostra os requisitos de uma norma e todos os equipamentos sujeitos a ela, "
        "seja por regulacao direta ou pela classe taxonomica"
    )

    def executar(self, session, params: ConformidadeNormativaParams) -> EnvelopeEvidencia:
        rec = session.run(
            "MATCH (n:Norma) WHERE n.id = $nid OR n.codigo = $nid RETURN n",
            parameters={"nid": params.norma_id},
        ).single()
        if rec is None:
            raise KeyError(f"Norma '{params.norma_id}' nao encontrada.")

        norma = rec["n"]
        norma_id = norma["id"]
        codigo = norma.get("codigo", norma_id)

        nos = [NoEvidencia(
            label="Norma", id=norma_id,
            propriedades={"codigo": codigo, "descricao": norma.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {norma_id}

        requisitos, criticos = [], 0
        for r in session.run(
            "MATCH (n:Norma {id: $nid})-[:TEM_REQUISITO]->(rq:Requisito) RETURN rq ORDER BY rq.id",
            parameters={"nid": norma_id},
        ):
            rq = r["rq"]
            if rq["id"] in ids_vistos:
                continue
            ids_vistos.add(rq["id"])
            requisitos.append(rq["id"])
            if rq.get("criticidade") == "alta":
                criticos += 1
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

        # Equipamento sujeito a norma por duas vias distintas: regulacao direta,
        # ou heranca da classe taxonomica. As duas contam, e a evidencia mostra
        # qual delas vale para cada equipamento.
        diretos, por_classe = set(), set()
        for r in session.run(
            """
            MATCH (eq:Equipamento)-[:REGULADO_POR]->(n:Norma {id: $nid})
            RETURN eq
            """,
            parameters={"nid": norma_id},
        ):
            eq = r["eq"]
            diretos.add(eq["id"])
            if eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))
            arestas.append(ArestaEvidencia(
                tipo="REGULADO_POR", origem_id=eq["id"], destino_id=norma_id,
            ))

        for r in session.run(
            """
            MATCH (eq:Equipamento)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
                  -[:REGULADO_POR]->(n:Norma {id: $nid})
            RETURN eq, ct
            """,
            parameters={"nid": norma_id},
        ):
            eq, ct = r["eq"], r["ct"]
            por_classe.add(eq["id"])
            if eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))
            if ct["id"] not in ids_vistos:
                ids_vistos.add(ct["id"])
                nos.append(NoEvidencia(
                    label="ClasseTaxonomia", id=ct["id"],
                    propriedades={"descricao": ct.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="REGULADO_POR", origem_id=ct["id"], destino_id=norma_id,
                ))
            arestas.append(ArestaEvidencia(
                tipo="CLASSIFICADO_COMO", origem_id=eq["id"], destino_id=ct["id"],
            ))

        alcancados = diretos | por_classe
        total_equip = contar(session, "MATCH (eq:Equipamento) RETURN count(eq) AS c")

        calculos = [
            CalculoEvidencia(
                nome="requisitos", formula="count(Requisito)",
                valor=len(requisitos), unidade="requisitos",
            ),
            CalculoEvidencia(
                nome="requisitos_criticidade_alta", formula="count(Requisito onde criticidade=alta)",
                valor=criticos, unidade="requisitos",
            ),
            CalculoEvidencia(
                nome="equipamentos_sujeitos", formula="count(distinct Equipamento alcancado)",
                valor=len(alcancados), unidade="equipamentos",
            ),
            CalculoEvidencia(
                nome="cobertura_do_parque",
                formula="equipamentos_sujeitos / total de Equipamento",
                valor=round(len(alcancados) / total_equip, 4) if total_equip else 0.0,
                unidade="fracao",
            ),
        ]

        lacunas = []
        if not requisitos:
            lacunas.append("Norma sem requisito cadastrado — alcance nao verificavel item a item.")
        if not alcancados:
            lacunas.append("Nenhum equipamento declarado como sujeito a esta norma.")

        return EnvelopeEvidencia(
            afirmacao=(
                f"A norma {codigo} impoe {len(requisitos)} requisito(s) "
                f"({criticos} de criticidade alta) e alcanca {len(alcancados)} "
                f"de {total_equip} equipamento(s) do parque — "
                f"{len(diretos)} por regulacao direta e {len(por_classe)} pela classe taxonomica."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[NormaEvidencia(codigo=codigo, descricao=norma.get("descricao", ""))],
            lacunas=lacunas,
        )
