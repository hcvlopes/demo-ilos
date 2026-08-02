from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class DefeitosResolvidosParams(BaseModel):
    limite: int = 10


class DefeitosResolvidos(IntencaoBase):
    """Defeitos ja encerrados, com o que foi feito e quanto tempo levou.

    Contraparte de `defeitos_abertos`. Serve para responder o que costuma
    resolver um modo de falha — a acao tomada esta declarada, entao a
    resposta nao depende de ler texto livre de nota.
    """

    nome = "defeitos_resolvidos"
    descricao = (
        "Lista defeitos ja encerrados com a acao que os resolveu, o tempo de "
        "execucao e o tempo entre deteccao e encerramento"
    )

    def executar(self, session, params: DefeitosResolvidosParams) -> EnvelopeEvidencia:
        registros = list(session.run(
            """
            MATCH (d:Defeito)
            WHERE d.status = 'resolvido'
            OPTIONAL MATCH (d)-[:DETECTADO_EM]->(eq:Equipamento)
            OPTIONAL MATCH (d)-[:RESOLVIDO_POR]->(at:AcaoTomada)
            OPTIONAL MATCH (d)-[:MANIFESTOU]->(mf:ModoFalha)
            RETURN d, eq, at, mf
            ORDER BY d.id
            LIMIT $lim
            """,
            parameters={"lim": params.limite},
        ))

        nos, arestas = [], []
        ids_vistos = set()
        duracoes, execucoes = [], []
        com_acao = 0

        for r in registros:
            d, eq, at, mf = r["d"], r.get("eq"), r.get("at"), r.get("mf")
            if d["id"] not in ids_vistos:
                ids_vistos.add(d["id"])
                nos.append(NoEvidencia(
                    label="Defeito", id=d["id"],
                    propriedades={
                        "descricao": d.get("descricao", ""),
                        "status": d.get("status", ""),
                    },
                ))
            det = d.get("data_deteccao_horas")
            enc = d.get("data_encerramento_horas")
            if det is not None and enc is not None:
                duracoes.append(float(enc) - float(det))

            if eq:
                if eq["id"] not in ids_vistos:
                    ids_vistos.add(eq["id"])
                    nos.append(NoEvidencia(
                        label="Equipamento", id=eq["id"],
                        propriedades={"descricao": eq.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="DETECTADO_EM", origem_id=d["id"], destino_id=eq["id"],
                ))

            if mf:
                if mf["id"] not in ids_vistos:
                    ids_vistos.add(mf["id"])
                    nos.append(NoEvidencia(
                        label="ModoFalha", id=mf["id"],
                        propriedades={"descricao": mf.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="MANIFESTOU", origem_id=d["id"], destino_id=mf["id"],
                ))

            if at:
                com_acao += 1
                if at["id"] not in ids_vistos:
                    ids_vistos.add(at["id"])
                    nos.append(NoEvidencia(
                        label="AcaoTomada", id=at["id"],
                        propriedades={
                            "descricao": at.get("descricao", ""),
                            "horas_execucao": at.get("horas_execucao", ""),
                        },
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="RESOLVIDO_POR", origem_id=d["id"], destino_id=at["id"],
                ))
                he = at.get("horas_execucao")
                if he is not None:
                    execucoes.append(float(he))

        calculos = [
            CalculoEvidencia(
                nome="defeitos_resolvidos", formula="count(Defeito onde status=resolvido)",
                valor=len(registros), unidade="defeitos",
            ),
        ]
        if duracoes:
            calculos.append(CalculoEvidencia(
                nome="tempo_medio_ate_encerramento",
                formula="media(data_encerramento_horas - data_deteccao_horas)",
                valor=round(sum(duracoes) / len(duracoes), 2), unidade="horas",
            ))
        if execucoes:
            calculos.append(CalculoEvidencia(
                nome="tempo_medio_de_execucao", formula="media(AcaoTomada.horas_execucao)",
                valor=round(sum(execucoes) / len(execucoes), 2), unidade="horas",
            ))

        lacunas = []
        if not registros:
            lacunas.append("Nenhum defeito encerrado registrado.")
        sem_acao = len(registros) - com_acao
        if sem_acao > 0:
            lacunas.append(f"{sem_acao} defeito(s) encerrado(s) sem acao tomada declarada.")

        return EnvelopeEvidencia(
            afirmacao=(
                f"{len(registros)} defeito(s) encerrado(s), {com_acao} com acao "
                f"tomada declarada."
                + (
                    f" Tempo medio ate encerramento: "
                    f"{round(sum(duracoes) / len(duracoes), 1)} horas de operacao."
                    if duracoes else ""
                )
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
