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

# Rotulos que o grupo de planejamento pode cobrir, na ordem em que sao
# reportados. A ontologia permite PLANEJADO_POR a partir de todos eles.
LABELS_PLANEJAVEIS = ["Edificacao", "Sistema", "Ativo", "Equipamento"]


class EscopoGrupoPlanejamentoParams(BaseModel):
    grupo_id: str


class EscopoGrupoPlanejamento(IntencaoBase):
    """O que um grupo de planejamento cobre, nivel a nivel da hierarquia.

    A mesma aresta PLANEJADO_POR parte de quatro rotulos diferentes. Sem
    percorrer todos, a resposta subestima o escopo — e um grupo que planeja a
    edificacao inteira pareceria nao planejar nada.
    """

    nome = "escopo_grupo_planejamento"
    descricao = (
        "Mostra o escopo de um grupo de planejamento por nivel da hierarquia "
        "e quanto do parque total ele cobre"
    )

    def executar(self, session, params: EscopoGrupoPlanejamentoParams) -> EnvelopeEvidencia:
        gp = resolver_no(session, "GrupoPlanejamento", params.grupo_id)
        grupo_id = gp["id"]

        nos = [NoEvidencia(
            label="GrupoPlanejamento", id=grupo_id,
            propriedades={"descricao": gp.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {grupo_id}
        calculos = []
        cobertura = {}

        for label in LABELS_PLANEJAVEIS:
            planejados = list(session.run(
                f"""
                MATCH (x:{label})-[:PLANEJADO_POR]->(gp:GrupoPlanejamento {{id: $gid}})
                RETURN x
                ORDER BY x.id
                """,
                parameters={"gid": grupo_id},
            ))
            total = contar(session, f"MATCH (x:{label}) RETURN count(x) AS c")
            cobertura[label] = (len(planejados), total)

            # Amostra no grafo, contagem completa nos calculos: 49 equipamentos
            # num painel de evidencia nao ajudam a ler nada.
            for r in planejados[:6]:
                x = r["x"]
                if x["id"] not in ids_vistos:
                    ids_vistos.add(x["id"])
                    nos.append(NoEvidencia(
                        label=label, id=x["id"],
                        propriedades={"descricao": x.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="PLANEJADO_POR", origem_id=x["id"], destino_id=grupo_id,
                ))

            calculos.append(CalculoEvidencia(
                nome=f"{label.lower()}_planejados",
                formula=f"count({label} PLANEJADO_POR grupo)",
                valor=len(planejados), unidade=label.lower(),
            ))
            if total:
                calculos.append(CalculoEvidencia(
                    nome=f"cobertura_{label.lower()}",
                    formula=f"{label} planejados / total de {label}",
                    valor=round(len(planejados) / total, 4), unidade="fracao",
                ))

        lacunas = []
        vazios = [lb for lb, (n, _t) in cobertura.items() if n == 0]
        if vazios:
            lacunas.append(
                f"Nenhum no planejado nos niveis: {', '.join(vazios)}.",
            )
        parciais = [
            lb for lb, (n, t) in cobertura.items() if 0 < n < t
        ]
        if parciais:
            lacunas.append(
                f"Cobertura parcial em: {', '.join(parciais)} — "
                f"parte do parque nao tem grupo de planejamento declarado.",
            )
        for label in LABELS_PLANEJAVEIS:
            n, _t = cobertura[label]
            if n > 6:
                lacunas.append(f"Grafo mostra 6 de {n} {label}(s) — calculos usam todos.")

        resumo = ", ".join(
            f"{n} de {t} {lb.lower()}(s)" for lb, (n, t) in cobertura.items() if n
        ) or "nenhum no"
        desc = gp.get("descricao", grupo_id)
        return EnvelopeEvidencia(
            afirmacao=f"O grupo {desc} planeja {resumo}.",
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
