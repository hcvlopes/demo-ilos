from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    NormaEvidencia,
)


class EtapasOrdemParams(BaseModel):
    ordem_id: str


class EtapasOrdem(IntencaoBase):
    """Sequencia de execucao de uma ordem, com quem executa cada etapa.

    A primeira etapa e sempre bloqueio de energia — nao por convencao de
    escrita, mas porque e requisito normativo. A norma correspondente vai no
    envelope para que a exigencia fique rastreavel ate a fonte.
    """

    nome = "etapas_ordem"
    descricao = (
        "Mostra as etapas de uma ordem de manutencao na ordem de execucao, "
        "a equipe responsavel e o defeito ou evento que a originou"
    )

    def executar(self, session, params: EtapasOrdemParams) -> EnvelopeEvidencia:
        rec = session.run(
            "MATCH (om:OrdemManutencao {id: $oid}) RETURN om",
            parameters={"oid": params.ordem_id},
        ).single()
        if rec is None:
            raise KeyError(f"Ordem de manutencao '{params.ordem_id}' nao encontrada.")

        om = rec["om"]
        nos = [NoEvidencia(
            label="OrdemManutencao", id=om["id"],
            propriedades={"descricao": om.get("descricao", ""), "tipo": om.get("tipo", "")},
        )]
        arestas = []
        ids_vistos = {om["id"]}

        etapas = []
        equipes = set()
        for r in session.run(
            """
            MATCH (om:OrdemManutencao {id: $oid})-[:TEM_ETAPA]->(et:Etapa)
            OPTIONAL MATCH (et)-[:EXECUTADA_POR]->(eqp:Equipe)
            RETURN et, eqp
            ORDER BY et.ordem
            """,
            parameters={"oid": params.ordem_id},
        ):
            et, eqp = r["et"], r.get("eqp")
            if et["id"] not in ids_vistos:
                ids_vistos.add(et["id"])
                etapas.append(et)
                nos.append(NoEvidencia(
                    label="Etapa", id=et["id"],
                    propriedades={
                        "descricao": et.get("descricao", ""),
                        "ordem": et.get("ordem", ""),
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="TEM_ETAPA", origem_id=params.ordem_id, destino_id=et["id"],
                ))
            if eqp:
                equipes.add(eqp["id"])
                if eqp["id"] not in ids_vistos:
                    ids_vistos.add(eqp["id"])
                    nos.append(NoEvidencia(
                        label="Equipe", id=eqp["id"],
                        propriedades={"descricao": eqp.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="EXECUTADA_POR", origem_id=et["id"], destino_id=eqp["id"],
                ))

        for rel, label in [("RESOLVE", "Defeito"), ("EXECUTADA_EM", "Equipamento")]:
            for r in session.run(
                f"MATCH (om:OrdemManutencao {{id: $oid}})-[:{rel}]->(x:{label}) RETURN x",
                parameters={"oid": params.ordem_id},
            ):
                x = r["x"]
                if x["id"] not in ids_vistos:
                    ids_vistos.add(x["id"])
                    nos.append(NoEvidencia(
                        label=label, id=x["id"],
                        propriedades={"descricao": x.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo=rel, origem_id=params.ordem_id, destino_id=x["id"],
                ))

        calculos = [
            CalculoEvidencia(
                nome="etapas", formula="count(Etapa)",
                valor=len(etapas), unidade="etapas",
            ),
            CalculoEvidencia(
                nome="equipes_envolvidas", formula="count(distinct Equipe)",
                valor=len(equipes), unidade="equipes",
            ),
        ]

        # A exigencia de bloqueio antes da intervencao vem da norma, nao do
        # plano: se ela estiver declarada no grafo, entra como evidencia.
        normas_ev = []
        for r in session.run(
            """
            MATCH (n:Norma)-[:TEM_REQUISITO]->(rq:Requisito)
            WHERE toLower(rq.descricao) CONTAINS 'bloqueio'
            RETURN n, rq
            """,
        ):
            n, rq = r["n"], r["rq"]
            if rq["id"] not in ids_vistos:
                ids_vistos.add(rq["id"])
                nos.append(NoEvidencia(
                    label="Requisito", id=rq["id"],
                    propriedades={
                        "descricao": rq.get("descricao", ""),
                        "criticidade": rq.get("criticidade", ""),
                    },
                ))
            normas_ev.append(NormaEvidencia(
                codigo=n.get("codigo", n["id"]), descricao=rq.get("descricao", ""),
            ))

        lacunas = []
        if not etapas:
            lacunas.append("Ordem sem etapas detalhadas.")
        if etapas and not equipes:
            lacunas.append("Etapas sem equipe responsavel atribuida.")
        primeira = etapas[0] if etapas else None
        if primeira and "bloqueio" not in primeira.get("descricao", "").lower():
            lacunas.append(
                "A primeira etapa nao e bloqueio de energia — verificar contra o "
                "requisito normativo aplicavel.",
            )

        return EnvelopeEvidencia(
            afirmacao=(
                f"A ordem {params.ordem_id} ({om.get('tipo', 'tipo nao declarado')}) "
                f"tem {len(etapas)} etapa(s) executadas por {len(equipes)} equipe(s)."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=normas_ev,
            lacunas=lacunas,
        )
