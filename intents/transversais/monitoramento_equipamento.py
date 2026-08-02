from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class MonitoramentoParams(BaseModel):
    equipamento_id: str


class MonitoramentoEquipamento(IntencaoBase):
    nome = "monitoramento_equipamento"
    descricao = "Mostra sensores, pontos de medicao e registros de condicao de um equipamento"

    def executar(self, session, params: MonitoramentoParams) -> EnvelopeEvidencia:
        r_eq = session.run(
            "MATCH (eq:Equipamento {id: $eid}) RETURN eq",
            parameters={"eid": params.equipamento_id},
        )
        rec = r_eq.single()
        if rec is None:
            raise KeyError(f"Equipamento '{params.equipamento_id}' nao encontrado.")

        eq_node = rec["eq"]
        nos = [NoEvidencia(
            label="Equipamento", id=eq_node["id"],
            propriedades={"descricao": eq_node.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {params.equipamento_id}

        r_sens = session.run(
            """
            MATCH (eq:Equipamento {id: $eid})-[:TEM_SENSOR]->(s:Sensor)
            RETURN s
            """,
            parameters={"eid": params.equipamento_id},
        )
        sensores = set()
        for record in r_sens:
            s = record["s"]
            if s and s["id"] not in ids_vistos:
                ids_vistos.add(s["id"])
                sensores.add(s["id"])
                nos.append(NoEvidencia(
                    label="Sensor", id=s["id"],
                    propriedades={
                        "descricao": s.get("descricao", ""),
                        "tipo": s.get("tipo", ""),
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="TEM_SENSOR", origem_id=params.equipamento_id, destino_id=s["id"],
                ))

        r_pm = session.run(
            """
            MATCH (eq:Equipamento {id: $eid})-[:TEM_PONTO]->(pm:PontoMedicao)
            RETURN pm
            """,
            parameters={"eid": params.equipamento_id},
        )
        pontos = set()
        for record in r_pm:
            pm = record["pm"]
            if pm and pm["id"] not in ids_vistos:
                ids_vistos.add(pm["id"])
                pontos.add(pm["id"])
                props = {"grandeza": pm.get("grandeza", "")}
                la = pm.get("limite_alarme")
                if la is not None:
                    props["limite_alarme"] = la
                nos.append(NoEvidencia(label="PontoMedicao", id=pm["id"], propriedades=props))
                arestas.append(ArestaEvidencia(
                    tipo="TEM_PONTO", origem_id=params.equipamento_id, destino_id=pm["id"],
                ))

        r_rc = session.run(
            """
            MATCH (eq:Equipamento {id: $eid})-[:TEM_REGISTRO]->(rc:RegistroCondicao)
            OPTIONAL MATCH (rc)-[:PARA_PONTO]->(pm:PontoMedicao)
            OPTIONAL MATCH (rc)-[:DETECTOU]->(d:Defeito)
            RETURN rc, pm.id AS pm_id, d
            ORDER BY rc.sequencia
            """,
            parameters={"eid": params.equipamento_id},
        )
        registros = []
        valores = []
        for record in r_rc:
            rc = record["rc"]
            if rc and rc["id"] not in ids_vistos:
                ids_vistos.add(rc["id"])
                registros.append(rc["id"])
                val = rc.get("valor")
                if val is not None:
                    valores.append(float(val))
                nos.append(NoEvidencia(
                    label="RegistroCondicao", id=rc["id"],
                    propriedades={
                        "valor": rc.get("valor", ""),
                        "sequencia": rc.get("sequencia", ""),
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="TEM_REGISTRO", origem_id=params.equipamento_id, destino_id=rc["id"],
                ))

            d = record.get("d")
            if d and d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={"descricao": d.get("descricao", ""), "status": d.get("status", "")},
                ))
                arestas.append(ArestaEvidencia(
                    tipo="DETECTOU", origem_id=rc["id"], destino_id=d["id"],
                ))

        calculos = [
            CalculoEvidencia(nome="sensores", formula="count(Sensor)", valor=len(sensores), unidade="sensores"),
            CalculoEvidencia(nome="pontos_medicao", formula="count(PontoMedicao)", valor=len(pontos), unidade="pontos"),
            CalculoEvidencia(nome="registros_condicao", formula="count(RegistroCondicao)", valor=len(registros), unidade="registros"),
        ]

        if valores:
            calculos.append(CalculoEvidencia(
                nome="ultimo_valor", formula="last(RegistroCondicao.valor)",
                valor=valores[-1], unidade="unidade_grandeza",
            ))
            if len(valores) >= 2:
                tendencia = valores[-1] - valores[0]
                calculos.append(CalculoEvidencia(
                    nome="tendencia", formula="ultimo - primeiro",
                    valor=tendencia, unidade="delta",
                ))

        lacunas = []
        if not sensores:
            lacunas.append("Nenhum sensor instalado neste equipamento.")
        if not pontos:
            lacunas.append("Nenhum ponto de medicao configurado.")
        if not registros:
            lacunas.append("Nenhum registro de condicao disponivel.")

        desc = eq_node.get("descricao", params.equipamento_id)
        return EnvelopeEvidencia(
            afirmacao=f"O equipamento {params.equipamento_id} ({desc}) possui {len(sensores)} sensor(es), "
                      f"{len(pontos)} ponto(s) de medicao e {len(registros)} registro(s) de condicao.",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
