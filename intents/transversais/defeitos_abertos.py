from pydantic import BaseModel, Field

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class DefeitosAbertosParams(BaseModel):
    limite: int = Field(default=20, description="Numero maximo de defeitos a retornar")


class DefeitosAbertos(IntencaoBase):
    nome = "defeitos_abertos"
    descricao = "Lista todos os defeitos abertos com equipamento, modo de falha e causa"

    def executar(self, session, params: DefeitosAbertosParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (d:Defeito {status: 'aberto'})-[:DETECTADO_EM]->(eq:Equipamento)
            OPTIONAL MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
            OPTIONAL MATCH (d)-[:MANIFESTOU]->(mf:ModoFalha)
            OPTIONAL MATCH (d)-[:CAUSADO_POR]->(cf:CausaFalha)
            RETURN d, eq, ct, mf, cf
            LIMIT $limite
            """,
            parameters={"limite": params.limite},
        )

        nos, arestas = [], []
        ids_vistos = set()
        count = 0

        for record in result:
            d = record["d"]
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                count += 1
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={"descricao": d.get("descricao", ""), "status": "aberto"},
                ))

            eq = record.get("eq")
            if eq and eq["id"] not in ids_vistos:
                ids_vistos.add(eq["id"])
                nos.append(NoEvidencia(
                    label="Equipamento", id=eq["id"],
                    propriedades={"descricao": eq.get("descricao", "")},
                ))
            if d and eq:
                arestas.append(ArestaEvidencia(
                    tipo="DETECTADO_EM", origem_id=d["id"], destino_id=eq["id"],
                ))

            mf = record.get("mf")
            if mf and mf["id"] not in ids_vistos:
                ids_vistos.add(mf["id"])
                nos.append(NoEvidencia(
                    label="ModoFalha", id=mf["id"],
                    propriedades={"descricao": mf.get("descricao", "")},
                ))
            if d and mf:
                arestas.append(ArestaEvidencia(
                    tipo="MANIFESTOU", origem_id=d["id"], destino_id=mf["id"],
                ))

            cf = record.get("cf")
            if cf and cf["id"] not in ids_vistos:
                ids_vistos.add(cf["id"])
                nos.append(NoEvidencia(
                    label="CausaFalha", id=cf["id"],
                    propriedades={"descricao": cf.get("descricao", "")},
                ))
            if d and cf:
                arestas.append(ArestaEvidencia(
                    tipo="CAUSADO_POR", origem_id=d["id"], destino_id=cf["id"],
                ))

        calculos = [
            CalculoEvidencia(
                nome="defeitos_abertos", formula="count(Defeito{status:aberto})",
                valor=count, unidade="defeitos",
            ),
        ]

        lacunas = []
        if count == 0:
            lacunas.append("Nenhum defeito aberto encontrado no grafo.")

        return EnvelopeEvidencia(
            afirmacao=f"Encontrado(s) {count} defeito(s) aberto(s) no sistema.",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
