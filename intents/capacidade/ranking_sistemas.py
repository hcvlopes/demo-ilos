from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
)


class RankingSistemasParams(BaseModel):
    edificacao_id: str = ""


class RankingSistemas(IntencaoBase):
    """Ordena sistemas pela taxa de falha agregada dos equipamentos.

    A agregacao trata o sistema como serie: a taxa do conjunto e a soma das
    taxas das classes dos equipamentos que o compoem. O intervalo sai da soma
    dos limites das classes, o que e um limite conservador e nao um IC exato
    — a soma so seria exata sob independencia entre componentes, que aqui nao
    esta demonstrada. A lacuna registra isso, porque metrica de
    confiabilidade sem IC nao e exibivel (regra 8) e IC mal rotulado e pior
    do que nenhum.
    """

    nome = "ranking_sistemas"
    descricao = (
        "Ordena os sistemas pela taxa de falha agregada, com intervalo, "
        "para comparar quais concentram risco"
    )

    def executar(self, session, params: RankingSistemasParams) -> EnvelopeEvidencia:
        if params.edificacao_id:
            rec = session.run(
                "MATCH (e:Edificacao {id: $eid}) RETURN e",
                parameters={"eid": params.edificacao_id},
            ).single()
            if rec is None:
                raise KeyError(f"Edificacao '{params.edificacao_id}' nao encontrada.")
            consulta = """
                MATCH (e:Edificacao {id: $eid})-[:CONTEM]->(sis:Sistema)
                MATCH (sis)-[:CONTEM]->(a:Ativo)<-[:PERTENCE]-(eq:Equipamento)
                MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
                OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
                RETURN sis, count(DISTINCT eq) AS n_equip,
                       sum(mc.lambda_hat) AS lambda_total,
                       sum(mc.ic_inferior) AS ic_inf,
                       sum(mc.ic_superior) AS ic_sup,
                       count(DISTINCT CASE WHEN mc IS NULL THEN eq END) AS sem_metrica
                ORDER BY lambda_total DESC
            """
            parametros = {"eid": params.edificacao_id}
            escopo = f"na edificacao {params.edificacao_id}"
        else:
            consulta = """
                MATCH (sis:Sistema)-[:CONTEM]->(a:Ativo)<-[:PERTENCE]-(eq:Equipamento)
                MATCH (eq)-[:CLASSIFICADO_COMO]->(ct:ClasseTaxonomia)
                OPTIONAL MATCH (ct)-[:TEM_METRICA]->(mc:MetricaConfiabilidade)
                RETURN sis, count(DISTINCT eq) AS n_equip,
                       sum(mc.lambda_hat) AS lambda_total,
                       sum(mc.ic_inferior) AS ic_inf,
                       sum(mc.ic_superior) AS ic_sup,
                       count(DISTINCT CASE WHEN mc IS NULL THEN eq END) AS sem_metrica
                ORDER BY lambda_total DESC
            """
            parametros = {}
            escopo = "no parque"

        registros = list(session.run(consulta, parameters=parametros))

        nos, arestas, calculos = [], [], []
        ids_vistos = set()
        sem_metrica_total = 0
        classificados = []

        for r in registros:
            sis = r["sis"]
            lam = r.get("lambda_total")
            if sis["id"] not in ids_vistos:
                ids_vistos.add(sis["id"])
                nos.append(NoEvidencia(
                    label="Sistema", id=sis["id"],
                    propriedades={
                        "descricao": sis.get("descricao", ""),
                        "equipamentos": r["n_equip"],
                    },
                ))
            sem_metrica_total += r.get("sem_metrica") or 0
            if lam is None:
                continue
            classificados.append((sis, float(lam)))
            calculos.append(CalculoEvidencia(
                nome=f"lambda_agregado_{sis['id']}",
                formula="soma(lambda_hat das classes dos equipamentos do sistema)",
                valor=round(float(lam), 8),
                unidade="falhas/h_op",
                ic_inferior=round(float(r["ic_inf"]), 8) if r.get("ic_inf") is not None else None,
                ic_superior=round(float(r["ic_sup"]), 8) if r.get("ic_sup") is not None else None,
            ))

        # Aresta de comparacao entre o pior e os demais, para o grafo mostrar
        # a ordenacao em vez de so uma nuvem de sistemas soltos.
        if len(classificados) >= 2:
            pior = classificados[0][0]
            for sis, _lam in classificados[1:]:
                arestas.append(ArestaEvidencia(
                    tipo="COMPARADO_COM", origem_id=pior["id"], destino_id=sis["id"],
                ))

        calculos.append(CalculoEvidencia(
            nome="sistemas_avaliados", formula="count(Sistema com metrica agregavel)",
            valor=len(classificados), unidade="sistemas",
        ))
        if len(classificados) >= 2:
            razao = classificados[0][1] / classificados[-1][1] if classificados[-1][1] else None
            if razao is not None:
                calculos.append(CalculoEvidencia(
                    nome="razao_pior_sobre_melhor",
                    formula="lambda_agregado(pior) / lambda_agregado(melhor)",
                    valor=round(razao, 2), unidade="x",
                ))

        lacunas = [
            (
                "O intervalo e a soma dos limites das classes: um limite "
                "conservador, nao um IC exato. Vale como IC apenas sob "
                "independencia entre componentes, que este grafo nao demonstra."
            ),
        ]
        if sem_metrica_total:
            lacunas.append(
                f"{sem_metrica_total} equipamento(s) sem metrica de confiabilidade "
                f"ficaram fora da soma.",
            )
        if not classificados:
            lacunas.append("Nenhum sistema com metrica agregavel.")

        if classificados:
            pior, lam_pior = classificados[0]
            afirmacao = (
                f"Entre {len(classificados)} sistema(s) {escopo}, o de maior taxa de "
                f"falha agregada e {pior['id']} ({pior.get('descricao', '')}), com "
                f"{lam_pior:.2e} falhas por hora de operacao."
            )
        else:
            afirmacao = f"Nenhum sistema {escopo} tem metrica de confiabilidade agregavel."

        return EnvelopeEvidencia(
            afirmacao=afirmacao,
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
