from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class ResumoSistemaParams(BaseModel):
    sistema_id: str


class ResumoSistema(IntencaoBase):
    nome = "resumo_sistema"
    descricao = "Resume um sistema: ativos, equipamentos, defeitos abertos e metricas de confiabilidade"

    def executar(self, session, params: ResumoSistemaParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (s:Sistema {id: $sid})
            OPTIONAL MATCH (s)-[:CONTEM]->(a:Ativo)
            OPTIONAL MATCH (eq:Equipamento)-[:PERTENCE]->(a)
            OPTIONAL MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
            OPTIONAL MATCH (d:Defeito {status: 'aberto'})-[:DETECTADO_EM]->(eq)
            RETURN s, a, eq, ct, mc, d
            """,
            parameters={"sid": params.sistema_id},
        )

        nos, arestas = [], []
        ids_vistos = set()
        sistema_node = None
        ativos, equipamentos, defeitos = set(), set(), set()
        lambdas = []

        for record in result:
            s = record["s"]
            if s and s["id"] not in ids_vistos:
                ids_vistos.add(s["id"])
                sistema_node = s
                nos.append(NoEvidencia(
                    label="Sistema", id=s["id"],
                    propriedades={"descricao": s.get("descricao", "")},
                ))

            a = record.get("a")
            if a and a["id"] not in ids_vistos:
                ids_vistos.add(a["id"])
                ativos.add(a["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=a["id"],
                    propriedades={"descricao": a.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="CONTEM", origem_id=params.sistema_id, destino_id=a["id"],
                ))

            eq = record.get("eq")
            if eq and eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                equipamentos.add(eq["id"])
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))
                if a:
                    arestas.append(ArestaEvidencia(
                        tipo="PERTENCE", origem_id=eq["id"], destino_id=a["id"],
                    ))

            mc = record.get("mc")
            if mc and mc["id"] not in ids_vistos:
                ids_vistos.add(mc["id"])
                lh = mc.get("lambda_hat")
                if lh is not None:
                    lambdas.append(lh)

            d = record.get("d")
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                defeitos.add(d["id"])
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={"descricao": d.get("descricao", ""), "status": "aberto"},
                ))

        if sistema_node is None:
            raise KeyError(f"Sistema '{params.sistema_id}' nao encontrado.")

        calculos = [
            CalculoEvidencia(
                nome="total_ativos", formula="count(Ativo)",
                valor=len(ativos), unidade="ativos",
            ),
            CalculoEvidencia(
                nome="total_equipamentos", formula="count(Equipamento)",
                valor=len(equipamentos), unidade="equipamentos",
            ),
            CalculoEvidencia(
                nome="defeitos_abertos", formula="count(Defeito{status:aberto})",
                valor=len(defeitos), unidade="defeitos",
            ),
        ]

        if lambdas:
            media_lambda = sum(lambdas) / len(lambdas)
            calculos.append(CalculoEvidencia(
                nome="lambda_medio_sistema",
                formula="mean(lambda_hat) por classe",
                valor=media_lambda,
                unidade="falhas/h_op",
            ))

        lacunas = []
        if not ativos:
            lacunas.append("Nenhum ativo encontrado neste sistema.")
        if not lambdas:
            lacunas.append("Nenhuma metrica de confiabilidade disponivel para equipamentos deste sistema.")

        desc = sistema_node.get("descricao", params.sistema_id)
        return EnvelopeEvidencia(
            afirmacao=f"O sistema {params.sistema_id} ({desc}) contem {len(ativos)} ativo(s), "
                      f"{len(equipamentos)} equipamento(s) e {len(defeitos)} defeito(s) aberto(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
