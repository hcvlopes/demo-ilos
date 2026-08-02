from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    contar,
    resolver_no,
)


class AcoesPorPapelParams(BaseModel):
    papel_id: str


class AcoesPorPapel(IntencaoBase):
    """O que um papel esta autorizado a fazer, e sobre quais modos de falha.

    Autorizacao e o terceiro pilar da tese, junto de dependencia e norma. Um
    sistema que so registra ordens sabe o que foi feito; nao sabe dizer se
    quem fez podia fazer. Aqui a permissao esta declarada como aresta.
    """

    nome = "acoes_por_papel"
    descricao = (
        "Lista as acoes que um papel esta autorizado a executar, com a "
        "complexidade de cada uma e os modos de falha a que se aplicam"
    )

    def executar(self, session, params: AcoesPorPapelParams) -> EnvelopeEvidencia:
        papel = resolver_no(session, "Papel", params.papel_id)
        papel_id = papel["id"]

        nos = [NoEvidencia(
            label="Papel", id=papel_id,
            propriedades={
                "descricao": papel.get("descricao", ""),
                "nivel": papel.get("nivel", ""),
            },
        )]
        arestas = []
        ids_vistos = {papel_id}

        acoes = []
        por_complexidade = {}
        modos_cobertos = set()

        for r in session.run(
            """
            MATCH (p:Papel {id: $pid})-[:AUTORIZA]->(ap:AcaoPermitida)
            OPTIONAL MATCH (ap)-[:APLICAVEL_MODO]->(mf:ModoFalha)
            RETURN ap, collect(DISTINCT mf) AS modos
            ORDER BY ap.id
            """,
            parameters={"pid": papel_id},
        ):
            ap, modos = r["ap"], r["modos"] or []
            if ap["id"] not in ids_vistos:
                ids_vistos.add(ap["id"])
                acoes.append(ap)
                cx = ap.get("complexidade", "nao declarada")
                por_complexidade[cx] = por_complexidade.get(cx, 0) + 1
                nos.append(NoEvidencia(
                    label="AcaoPermitida", id=ap["id"],
                    propriedades={
                        "descricao": ap.get("descricao", ""),
                        "tipo": ap.get("tipo", ""),
                        "complexidade": cx,
                    },
                ))
                arestas.append(ArestaEvidencia(
                    tipo="AUTORIZA", origem_id=papel_id, destino_id=ap["id"],
                ))
            for mf in modos:
                if mf is None:
                    continue
                modos_cobertos.add(mf["id"])
                if mf["id"] not in ids_vistos:
                    ids_vistos.add(mf["id"])
                    nos.append(NoEvidencia(
                        label="ModoFalha", id=mf["id"],
                        propriedades={"descricao": mf.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="APLICAVEL_MODO", origem_id=ap["id"], destino_id=mf["id"],
                ))

        total_acoes = contar(session, "MATCH (ap:AcaoPermitida) RETURN count(ap) AS c")
        total_modos = contar(session, "MATCH (mf:ModoFalha) RETURN count(mf) AS c")

        calculos = [
            CalculoEvidencia(
                nome="acoes_autorizadas", formula="count(AcaoPermitida via AUTORIZA)",
                valor=len(acoes), unidade="acoes",
            ),
            CalculoEvidencia(
                nome="fracao_do_catalogo", formula="acoes_autorizadas / total de AcaoPermitida",
                valor=round(len(acoes) / total_acoes, 4) if total_acoes else 0.0,
                unidade="fracao",
            ),
            CalculoEvidencia(
                nome="modos_de_falha_cobertos", formula="count(distinct ModoFalha aplicavel)",
                valor=len(modos_cobertos), unidade="modos",
            ),
            CalculoEvidencia(
                nome="cobertura_dos_modos", formula="modos_cobertos / total de ModoFalha",
                valor=round(len(modos_cobertos) / total_modos, 4) if total_modos else 0.0,
                unidade="fracao",
            ),
        ]
        for cx, n in sorted(por_complexidade.items()):
            calculos.append(CalculoEvidencia(
                nome=f"acoes_complexidade_{cx}", formula=f"count(AcaoPermitida complexidade={cx})",
                valor=n, unidade="acoes",
            ))

        lacunas = []
        if not acoes:
            lacunas.append("Papel sem nenhuma acao autorizada.")
        nao_cobertos = total_modos - len(modos_cobertos)
        if nao_cobertos > 0:
            lacunas.append(
                f"{nao_cobertos} modo(s) de falha sem acao autorizada para este papel — "
                f"exigem escalonamento.",
            )

        desc = papel.get("descricao", papel_id)
        return EnvelopeEvidencia(
            afirmacao=(
                f"O papel {desc} esta autorizado a executar {len(acoes)} de "
                f"{total_acoes} acao(oes) do catalogo, cobrindo {len(modos_cobertos)} "
                f"de {total_modos} modo(s) de falha."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
