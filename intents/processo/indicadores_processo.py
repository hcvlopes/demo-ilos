from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    resolver_no,
)


class IndicadoresProcessoParams(BaseModel):
    processo_id: str = ""


class IndicadoresProcesso(IntencaoBase):
    """Indicadores do processo, medido contra meta.

    O indicador tinha `meta` e nenhuma medicao, entao "esta atendendo?" nao
    tinha resposta e o no era decoracao. Cada indicador agora carrega
    `valor_atual` e a `formula` que o produziu — a resposta pode dizer o
    numero e de onde ele veio.
    """

    nome = "indicadores_processo"
    descricao = (
        "Compara cada indicador de um processo com sua meta, dizendo a formula "
        "que produziu o valor medido"
    )

    def executar(self, session, params: IndicadoresProcessoParams) -> EnvelopeEvidencia:
        proc = resolver_no(session, "ProcessoOperacional", params.processo_id)
        pid = proc["id"]

        nos = [NoEvidencia(
            label="ProcessoOperacional", id=pid,
            propriedades={
                "descricao": proc.get("descricao", ""),
                "regime": proc.get("regime", ""),
                "horas_operacao_ano": proc.get("horas_operacao_ano", ""),
            },
        )]
        arestas = []
        calculos = []
        atendem, abaixo, sem_medicao = [], [], []

        for r in session.run(
            "MATCH (i:Indicador)-[:MEDE]->(p:ProcessoOperacional {id: $pid}) RETURN i ORDER BY i.id",
            parameters={"pid": pid},
        ):
            i = r["i"]
            meta = i.get("meta")
            atual = i.get("valor_atual")
            unidade = i.get("unidade", "")
            desc = i.get("descricao", i["id"])

            nos.append(NoEvidencia(
                label="Indicador", id=i["id"],
                propriedades={
                    "descricao": desc, "meta": meta, "valor_atual": atual,
                    "unidade": unidade, "formula": i.get("formula", ""),
                },
            ))
            arestas.append(ArestaEvidencia(
                tipo="MEDE", origem_id=i["id"], destino_id=pid,
            ))

            if atual is None:
                sem_medicao.append(desc)
                continue

            calculos.append(CalculoEvidencia(
                nome=i["id"].lower().replace("-", "_"),
                formula=i.get("formula", "nao declarada"),
                valor=float(atual), unidade=unidade,
            ))
            calculos.append(CalculoEvidencia(
                nome=f"{i['id'].lower().replace('-', '_')}_vs_meta",
                formula="valor_atual - meta",
                valor=round(float(atual) - float(meta), 4), unidade=unidade,
            ))
            if float(atual) >= float(meta):
                atendem.append(f"{desc} ({atual} {unidade}, meta {meta})")
            else:
                abaixo.append(f"{desc} ({atual} {unidade}, meta {meta})")

        lacunas = []
        if sem_medicao:
            lacunas.append(
                f"{len(sem_medicao)} indicador(es) sem valor medido: "
                f"{', '.join(sem_medicao)}.",
            )
        if not nos[1:]:
            lacunas.append("Processo sem indicador declarado.")

        partes = []
        if atendem:
            partes.append(f"atende {len(atendem)} — {'; '.join(atendem)}")
        if abaixo:
            partes.append(f"esta abaixo em {len(abaixo)} — {'; '.join(abaixo)}")

        return EnvelopeEvidencia(
            afirmacao=(
                f"O processo {proc.get('descricao', pid)} "
                + ("; ".join(partes) if partes else "nao tem indicador medido")
                + "."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
