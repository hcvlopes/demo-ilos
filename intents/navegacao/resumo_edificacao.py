from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class ResumoEdificacaoParams(BaseModel):
    edificacao_id: str


class ResumoEdificacao(IntencaoBase):
    nome = "resumo_edificacao"
    descricao = "Resume uma edificacao ou planta: sistemas, ativos, equipamentos e defeitos abertos"

    def executar(self, session, params: ResumoEdificacaoParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (ed:Edificacao {id: $eid})
            OPTIONAL MATCH (ed)-[:CONTEM]->(s:Sistema)
            OPTIONAL MATCH (s)-[:CONTEM]->(a:Ativo)
            OPTIONAL MATCH (eq:Equipamento)-[:PERTENCE]->(a)
            OPTIONAL MATCH (d:Defeito {status: 'aberto'})-[:DETECTADO_EM]->(eq)
            RETURN ed, s, a, eq, d
            """,
            parameters={"eid": params.edificacao_id},
        )

        nos, arestas = [], []
        ids_vistos = set()
        edif_node = None
        sistemas, ativos, equipamentos, defeitos = set(), set(), set(), set()

        for record in result:
            ed = record["ed"]
            if ed and ed["id"] not in ids_vistos:
                ids_vistos.add(ed["id"])
                edif_node = ed
                nos.append(NoEvidencia(
                    label="Edificacao", id=ed["id"],
                    propriedades={"descricao": ed.get("descricao", "")},
                ))

            s = record.get("s")
            if s and s["id"] not in ids_vistos:
                ids_vistos.add(s["id"])
                sistemas.add(s["id"])
                nos.append(NoEvidencia(
                    label="Sistema", id=s["id"],
                    propriedades={"descricao": s.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="CONTEM", origem_id=params.edificacao_id, destino_id=s["id"],
                ))

            a = record.get("a")
            if a and a["id"] not in ids_vistos:
                ids_vistos.add(a["id"])
                ativos.add(a["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=a["id"],
                    propriedades={"descricao": a.get("descricao", "")},
                ))
                if s:
                    arestas.append(ArestaEvidencia(
                        tipo="CONTEM", origem_id=s["id"], destino_id=a["id"],
                    ))

            eq = record.get("eq")
            if eq and eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                equipamentos.add(eq["id"])

            d = record.get("d")
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                defeitos.add(d["id"])

        if edif_node is None:
            raise KeyError(f"Edificacao '{params.edificacao_id}' nao encontrada.")

        calculos = [
            CalculoEvidencia(nome="total_sistemas", formula="count(Sistema)", valor=len(sistemas), unidade="sistemas"),
            CalculoEvidencia(nome="total_ativos", formula="count(Ativo)", valor=len(ativos), unidade="ativos"),
            CalculoEvidencia(nome="total_equipamentos", formula="count(Equipamento)", valor=len(equipamentos), unidade="equipamentos"),
            CalculoEvidencia(nome="defeitos_abertos", formula="count(Defeito{status:aberto})", valor=len(defeitos), unidade="defeitos"),
        ]

        lacunas = []
        if not sistemas:
            lacunas.append("Nenhum sistema encontrado nesta edificacao.")

        desc = edif_node.get("descricao", params.edificacao_id)
        return EnvelopeEvidencia(
            afirmacao=f"A edificacao {params.edificacao_id} ({desc}) contem {len(sistemas)} sistema(s), "
                      f"{len(ativos)} ativo(s), {len(equipamentos)} equipamento(s) e {len(defeitos)} defeito(s) aberto(s).",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
