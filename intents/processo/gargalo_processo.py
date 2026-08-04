from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    resolver_no,
)


class GargaloProcessoParams(BaseModel):
    processo_id: str = ""


class GargaloProcesso(IntencaoBase):
    """Qual estagio do processo concentra risco, e por que.

    Gargalo aqui nao e o estagio mais lento — o grafo nao declara tempo de
    ciclo. E o estagio de maior taxa de falha agregada, ponderada pelo que a
    perda dele significa: estagio essencial sem paralelo para o processo,
    estagio paralelo degrada.

    A ponderacao esta explicita nos calculos justamente porque "gargalo" e
    palavra ambigua, e a resposta precisa dizer em que sentido usa a palavra.
    """

    nome = "gargalo_processo"
    descricao = (
        "Identifica o estagio de maior risco de um processo, combinando taxa "
        "de falha agregada com o efeito da perda do estagio"
    )

    def executar(self, session, params: GargaloProcessoParams) -> EnvelopeEvidencia:
        proc = resolver_no(session, "ProcessoOperacional", params.processo_id)
        pid = proc["id"]

        nos = [NoEvidencia(
            label="ProcessoOperacional", id=pid,
            propriedades={"descricao": proc.get("descricao", ""), "regime": proc.get("regime", "")},
        )]
        arestas = []
        ids_vistos = {pid}

        registros = list(session.run(
            """
            MATCH (p:ProcessoOperacional {id: $pid})-[r:REQUER]->(f:Funcao)
            MATCH (a:Ativo)-[:DESEMPENHA]->(f)
            OPTIONAL MATCH (a)<-[:PERTENCE]-(eq:Equipamento)-[:CLASSIFICADO_COMO]->
                           (:ClasseTaxonomia)-[:TEM_METRICA]->(m:MetricaConfiabilidade)
            RETURN r.ordem AS ordem, r.criticidade AS criticidade, r.posicao AS posicao,
                   f AS funcao, a AS ativo,
                   sum(m.lambda_hat) AS lambda_estagio,
                   sum(m.ic_superior) AS ic_sup,
                   sum(m.ic_inferior) AS ic_inf,
                   count(DISTINCT eq) AS equipamentos
            ORDER BY r.ordem, f.id
            """,
            parameters={"pid": pid},
        ))

        # Agrupa por ordem: funcoes na mesma ordem sao o mesmo estagio.
        por_ordem: dict[int, dict] = {}
        for reg in registros:
            posicao = reg.get("posicao") or "fluxo"
            if posicao != "fluxo":
                continue
            ordem = int(reg.get("ordem") or 0)
            grupo = por_ordem.setdefault(ordem, {
                "funcoes": [], "lambda": 0.0, "ic_inf": 0.0, "ic_sup": 0.0,
                "equipamentos": 0, "criticidade": reg.get("criticidade") or "nao declarada",
            })
            grupo["funcoes"].append(reg["funcao"])
            grupo["lambda"] += float(reg.get("lambda_estagio") or 0.0)
            grupo["ic_inf"] += float(reg.get("ic_inf") or 0.0)
            grupo["ic_sup"] += float(reg.get("ic_sup") or 0.0)
            grupo["equipamentos"] += int(reg.get("equipamentos") or 0)

            f, a = reg["funcao"], reg["ativo"]
            for no, label in [(f, "Funcao"), (a, "Ativo")]:
                if no and no["id"] not in ids_vistos:
                    ids_vistos.add(no["id"])
                    nos.append(NoEvidencia(
                        label=label, id=no["id"],
                        propriedades={"descricao": no.get("descricao", "")},
                    ))
            arestas.append(ArestaEvidencia(
                tipo="REQUER", origem_id=pid, destino_id=f["id"],
                propriedades={"ordem": ordem},
            ))
            if a:
                arestas.append(ArestaEvidencia(
                    tipo="DESEMPENHA", origem_id=a["id"], destino_id=f["id"],
                ))

        calculos = []
        ranking = []
        for ordem in sorted(por_ordem):
            g = por_ordem[ordem]
            paralelo = len(g["funcoes"]) > 1
            # Estagio paralelo perde peso: a perda de uma das funcoes degrada
            # em vez de parar. O peso e 1 para estagio unico, 0.5 para paralelo.
            peso = 0.5 if paralelo else 1.0
            risco = g["lambda"] * peso
            ranking.append((risco, ordem, g, paralelo))
            calculos.append(CalculoEvidencia(
                nome=f"lambda_estagio_{ordem}",
                formula="soma(lambda_hat das classes dos equipamentos do estagio)",
                valor=round(g["lambda"], 8), unidade="falhas/h_op",
                ic_inferior=round(g["ic_inf"], 8) or None,
                ic_superior=round(g["ic_sup"], 8) or None,
            ))
            calculos.append(CalculoEvidencia(
                nome=f"risco_ponderado_estagio_{ordem}",
                formula="lambda_estagio * (0.5 se estagio paralelo, 1.0 se unico)",
                valor=round(risco, 8), unidade="falhas/h_op",
            ))

        ranking.sort(key=lambda t: t[0], reverse=True)

        lacunas = [
            (
                "Gargalo aqui significa maior risco de falha, nao maior tempo "
                "de ciclo: o grafo nao declara tempo de processamento."
            ),
            (
                "O intervalo e a soma dos limites das classes — limite "
                "conservador, nao IC exato (vale sob independencia, que este "
                "grafo nao demonstra)."
            ),
        ]
        if not ranking:
            lacunas.append("Processo sem estagio de fluxo com metrica agregavel.")
            afirmacao = f"O processo {proc.get('descricao', pid)} nao tem estagio avaliavel."
        else:
            risco, ordem, g, paralelo = ranking[0]
            nomes = " + ".join(f.get("descricao", f["id"]) for f in g["funcoes"])
            afirmacao = (
                f"No processo {proc.get('descricao', pid)}, o estagio de maior risco "
                f"e o {ordem} ({nomes}), com taxa agregada de {g['lambda']:.2e} "
                f"falhas por hora de operacao em {g['equipamentos']} equipamento(s). "
                + (
                    "O estagio tem funcoes em paralelo, entao perder uma degrada o "
                    "processo em vez de para-lo."
                    if paralelo else
                    "O estagio nao tem paralelo: perde-lo interrompe o fluxo."
                )
            )

        return EnvelopeEvidencia(
            afirmacao=afirmacao,
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
