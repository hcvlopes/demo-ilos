from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class CadeiaFalhaParams(BaseModel):
    defeito_id: str


class CadeiaFalha(IntencaoBase):
    nome = "cadeia_falha"
    descricao = "Mostra a cadeia completa de falha: defeito, eventos, modo, causa, mecanismo, notas, ordens e acoes tomadas"

    def executar(self, session, params: CadeiaFalhaParams) -> EnvelopeEvidencia:
        result = session.run(
            """
            MATCH (d:Defeito {id: $did})
            OPTIONAL MATCH (d)-[:DETECTADO_EM]->(eq:Equipamento)
            OPTIONAL MATCH (d)-[:MANIFESTOU]->(mf:ModoFalha)
            OPTIONAL MATCH (d)-[:CAUSADO_POR]->(cf:CausaFalha)
            OPTIONAL MATCH (d)-[:VIA_MECANISMO]->(mec:MecanismoFalha)
            OPTIONAL MATCH (d)-[:EVOLUIU_PARA]->(ev:EventoFalha)
            OPTIONAL MATCH (d)-[:GEROU]->(nm:NotaManutencao)
            OPTIONAL MATCH (nm)-[:GEROU_ORDEM]->(om:OrdemManutencao)
            OPTIONAL MATCH (d)-[:RESOLVIDO_POR]->(at:AcaoTomada)
            RETURN d, eq, mf, cf, mec, ev, nm, om, at
            """,
            parameters={"did": params.defeito_id},
        )

        nos, arestas = [], []
        ids_vistos = set()
        defeito_node = None
        eventos, notas, ordens, acoes = set(), set(), set(), set()

        for record in result:
            d = record["d"]
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                defeito_node = d
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={"descricao": d.get("descricao", ""), "status": d.get("status", "")},
                ))

            for key, label, rel in [
                ("eq", "Equipamento", "DETECTADO_EM"),
                ("mf", "ModoFalha", "MANIFESTOU"),
                ("cf", "CausaFalha", "CAUSADO_POR"),
                ("mec", "MecanismoFalha", "VIA_MECANISMO"),
            ]:
                node = record.get(key)
                if node and node["id"] not in ids_vistos:
                    ids_vistos.add(node["id"])
                    nos.append(NoEvidencia(
                        label=label, id=node["id"],
                        propriedades={"descricao": node.get("descricao", "")},
                    ))
                    arestas.append(ArestaEvidencia(
                        tipo=rel, origem_id=params.defeito_id, destino_id=node["id"],
                    ))

            ev = record.get("ev")
            if ev and ev["id"] not in ids_vistos:
                ids_vistos.add(ev["id"])
                eventos.add(ev["id"])
                nos.append(NoEvidencia(
                    label="EventoFalha", id=ev["id"],
                    propriedades={
                        "timestamp_horas_operacao": ev.get("timestamp_horas_operacao", ""),
                        "ano": ev.get("ano", ""),
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="EVOLUIU_PARA", origem_id=params.defeito_id, destino_id=ev["id"],
                ))

            nm = record.get("nm")
            if nm and nm["id"] not in ids_vistos:
                ids_vistos.add(nm["id"])
                notas.add(nm["id"])
                nos.append(NoEvidencia(
                    label="NotaManutencao", id=nm["id"],
                    propriedades={"descricao": nm.get("descricao", ""), "tipo": nm.get("tipo", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="GEROU", origem_id=params.defeito_id, destino_id=nm["id"],
                ))

            om = record.get("om")
            if om and om["id"] not in ids_vistos:
                ids_vistos.add(om["id"])
                ordens.add(om["id"])
                nos.append(NoEvidencia(
                    label="OrdemManutencao", id=om["id"],
                    propriedades={"descricao": om.get("descricao", ""), "tipo": om.get("tipo", "")},
                ))
                if nm:
                    arestas.append(ArestaEvidencia(
                        tipo="GEROU_ORDEM", origem_id=nm["id"], destino_id=om["id"],
                    ))

            at = record.get("at")
            if at and at["id"] not in ids_vistos:
                ids_vistos.add(at["id"])
                acoes.add(at["id"])
                nos.append(NoEvidencia(
                    label="AcaoTomada", id=at["id"],
                    propriedades={"descricao": at.get("descricao", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="RESOLVIDO_POR", origem_id=params.defeito_id, destino_id=at["id"],
                ))

        if defeito_node is None:
            raise KeyError(f"Defeito '{params.defeito_id}' nao encontrado.")

        lacunas = []
        if not eventos:
            lacunas.append("Defeito sem evento de falha associado.")
        if not notas:
            lacunas.append("Defeito sem nota de manutencao gerada.")
        if not ordens:
            lacunas.append("Nenhuma ordem de manutencao gerada a partir deste defeito.")
        if not acoes:
            lacunas.append("Defeito sem acao tomada registrada.")

        desc = defeito_node.get("descricao", params.defeito_id)
        return EnvelopeEvidencia(
            afirmacao=f"Cadeia de falha do defeito {params.defeito_id} ({desc}): "
                      f"{len(eventos)} evento(s), {len(notas)} nota(s), "
                      f"{len(ordens)} ordem(ns), {len(acoes)} acao(oes) tomada(s).",
            nos=nos,
            arestas=arestas,
            calculos=[],
            normas=[],
            lacunas=lacunas,
        )
