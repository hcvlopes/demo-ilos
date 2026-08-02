from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    resolver_no,
)


class CargaCentroTrabalhoParams(BaseModel):
    centro_id: str


class CargaCentroTrabalho(IntencaoBase):
    """Quanto parque um centro de manutencao atende, e com que carga aberta.

    Pergunta de dimensionamento: nao e quantas ordens existem, mas quantas
    recaem sobre uma equipe. A relacao equipamento-centro esta declarada,
    entao a conta atravessa a hierarquia sem depender de rateio manual.
    """

    nome = "carga_centro_trabalho"
    descricao = (
        "Mostra o parque atendido por um centro de trabalho, os defeitos "
        "abertos nesse parque e a distribuicao por sistema"
    )

    def executar(self, session, params: CargaCentroTrabalhoParams) -> EnvelopeEvidencia:
        ct = resolver_no(session, "CentroTrabalho", params.centro_id)
        centro_id = ct["id"]

        nos = [NoEvidencia(
            label="CentroTrabalho", id=centro_id,
            propriedades={"descricao": ct.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {centro_id}

        equipamentos = list(session.run(
            """
            MATCH (eq:Equipamento)-[:MANTIDO_POR]->(ct:CentroTrabalho {id: $cid})
            RETURN eq
            ORDER BY eq.id
            """,
            parameters={"cid": centro_id},
        ))

        # Amostra dos equipamentos vai para o grafo; a contagem cobre todos.
        # Sem isso o painel de evidencia viraria uma lista de 49 nos.
        for r in equipamentos[:12]:
            eq = r["eq"]
            if eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))
            arestas.append(ArestaEvidencia(
                tipo="MANTIDO_POR", origem_id=eq["id"], destino_id=centro_id,
            ))

        defeitos = list(session.run(
            """
            MATCH (d:Defeito)-[:DETECTADO_EM]->(eq:Equipamento)-[:MANTIDO_POR]->(:CentroTrabalho {id: $cid})
            WHERE d.status = 'aberto'
            RETURN d, eq
            ORDER BY d.id
            """,
            parameters={"cid": centro_id},
        ))
        for r in defeitos:
            d, eq = r["d"], r["eq"]
            if d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={
                        "descricao": d.get("descricao", ""),
                        "status": d.get("status", ""),
                    },
                ))
            if eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))
            arestas.append(ArestaEvidencia(
                tipo="DETECTADO_EM", origem_id=d["id"], destino_id=eq["id"],
            ))

        por_sistema = list(session.run(
            """
            MATCH (eq:Equipamento)-[:MANTIDO_POR]->(:CentroTrabalho {id: $cid})
            MATCH (eq)-[:PERTENCE]->(:Ativo)<-[:CONTEM]-(sis:Sistema)
            RETURN sis.id AS sid, sis.descricao AS sdesc, count(DISTINCT eq) AS n
            ORDER BY n DESC
            """,
            parameters={"cid": centro_id},
        ))
        for r in por_sistema:
            if r["sid"] not in ids_vistos:
                ids_vistos.add(r["sid"])
                nos.append(NoEvidencia(
                    label="Sistema", id=r["sid"],
                    propriedades={"descricao": r["sdesc"] or ""},
                ))

        n_equip = len(equipamentos)
        calculos = [
            CalculoEvidencia(
                nome="equipamentos_atendidos", formula="count(Equipamento MANTIDO_POR centro)",
                valor=n_equip, unidade="equipamentos",
            ),
            CalculoEvidencia(
                nome="defeitos_abertos", formula="count(Defeito aberto no parque atendido)",
                valor=len(defeitos), unidade="defeitos",
            ),
            CalculoEvidencia(
                nome="defeitos_por_equipamento", formula="defeitos_abertos / equipamentos_atendidos",
                valor=round(len(defeitos) / n_equip, 4) if n_equip else 0.0,
                unidade="defeitos/equipamento",
            ),
            CalculoEvidencia(
                nome="sistemas_atendidos", formula="count(distinct Sistema)",
                valor=len(por_sistema), unidade="sistemas",
            ),
        ]

        lacunas = []
        if not equipamentos:
            lacunas.append("Nenhum equipamento declarado como mantido por este centro.")
        if len(equipamentos) > 12:
            lacunas.append(
                f"Grafo mostra 12 de {n_equip} equipamentos — os calculos usam todos.",
            )

        desc = ct.get("descricao", centro_id)
        return EnvelopeEvidencia(
            afirmacao=(
                f"O centro {desc} atende {n_equip} equipamento(s) em "
                f"{len(por_sistema)} sistema(s), com {len(defeitos)} defeito(s) aberto(s)."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
