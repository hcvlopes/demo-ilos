from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    contar,
)


class ConsequenciaNotasParams(BaseModel):
    equipamento_id: str


class ConsequenciaNotas(IntencaoBase):
    """Distribuicao das notas de um equipamento por consequencia declarada.

    Contar notas nao diz nada: cem notas sem impacto imediato valem menos que
    tres que pararam a producao. A consequencia esta declarada no grafo, entao
    a resposta pode ser ponderada em vez de somada.
    """

    nome = "consequencia_notas"
    descricao = (
        "Agrupa as notas de manutencao de um equipamento pela consequencia "
        "declarada, com a severidade de cada grupo"
    )

    def executar(self, session, params: ConsequenciaNotasParams) -> EnvelopeEvidencia:
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

        grupos = list(session.run(
            """
            MATCH (nm:NotaManutencao)-[:ATRIBUIDA]->(eq:Equipamento {id: $eid})
            MATCH (nm)-[:ATRELADA]->(c:ConsequenciaNota)
            RETURN c, count(nm) AS quantas
            ORDER BY quantas DESC
            """,
            parameters={"eid": params.equipamento_id},
        ))

        total_notas = contar(
            session,
            "MATCH (nm:NotaManutencao)-[:ATRIBUIDA]->(:Equipamento {id: $eid}) "
            "RETURN count(nm) AS c",
            {"eid": params.equipamento_id},
        )

        calculos = []
        classificadas = 0
        alta_severidade = 0

        for r in grupos:
            c, quantas = r["c"], r["quantas"]
            classificadas += quantas
            if c.get("severidade") == "alta":
                alta_severidade += quantas
            if c["id"] not in ids_vistos:
                ids_vistos.add(c["id"])
                nos.append(NoEvidencia(
                    label="ConsequenciaNota", id=c["id"],
                    propriedades={
                        "descricao": c.get("descricao", ""),
                        "severidade": c.get("severidade", ""),
                    },
                ))
            arestas.append(ArestaEvidencia(
                tipo="ATRELADA", origem_id=params.equipamento_id, destino_id=c["id"],
                propriedades={"notas": quantas},
            ))
            calculos.append(CalculoEvidencia(
                nome=f"notas_{c['id']}",
                formula=f"count(NotaManutencao ATRELADA {c['id']})",
                valor=quantas, unidade="notas",
            ))

        calculos.append(CalculoEvidencia(
            nome="notas_total", formula="count(NotaManutencao ATRIBUIDA equipamento)",
            valor=total_notas, unidade="notas",
        ))
        calculos.append(CalculoEvidencia(
            nome="fracao_severidade_alta",
            formula="notas com consequencia de severidade alta / total",
            valor=round(alta_severidade / total_notas, 4) if total_notas else 0.0,
            unidade="fracao",
        ))

        lacunas = []
        nao_classificadas = total_notas - classificadas
        if nao_classificadas > 0:
            lacunas.append(
                f"{nao_classificadas} nota(s) sem consequencia declarada — "
                f"nao entram na ponderacao.",
            )
        if total_notas == 0:
            lacunas.append("Equipamento sem nota de manutencao registrada.")

        desc = eq.get("descricao", params.equipamento_id)
        return EnvelopeEvidencia(
            afirmacao=(
                f"O equipamento {params.equipamento_id} ({desc}) acumula {total_notas} "
                f"nota(s) de manutencao, distribuidas em {len(grupos)} consequencia(s) "
                f"declarada(s). {alta_severidade} delas tem severidade alta."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
