from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    resolver_no,
)


class CadeiaProcessoParams(BaseModel):
    processo_id: str = ""


class CadeiaProcesso(IntencaoBase):
    """A sequencia do processo, estagio a estagio, com quem executa cada um.

    Antes da migration 003 o processo era um saco plano de funcoes: dava para
    contar, nao para ordenar. Com `ordem` e `posicao` na aresta REQUER, a
    resposta consegue dizer o que vem antes de que, e separar o que esta no
    fluxo do que e suporte transversal.

    Estagio com duas funcoes na mesma ordem e estagio PARALELO — a distincao
    importa porque perder uma das duas degrada, perder as duas para.
    """

    nome = "cadeia_processo"
    descricao = (
        "Mostra a sequencia de estagios de um processo operacional, quais "
        "ativos executam cada estagio, e o que e suporte transversal"
    )

    def executar(self, session, params: CadeiaProcessoParams) -> EnvelopeEvidencia:
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
        ids_vistos = {pid}

        registros = list(session.run(
            """
            MATCH (p:ProcessoOperacional {id: $pid})-[r:REQUER]->(f:Funcao)
            OPTIONAL MATCH (a:Ativo)-[:DESEMPENHA]->(f)
            RETURN r.ordem AS ordem, r.criticidade AS criticidade,
                   r.posicao AS posicao, f AS funcao, a AS ativo
            ORDER BY r.ordem, f.id
            """,
            parameters={"pid": pid},
        ))

        estagios: dict[int, list[str]] = {}
        suporte: list[str] = []
        essenciais = 0

        for reg in registros:
            f, a = reg["funcao"], reg.get("ativo")
            posicao = reg.get("posicao") or "fluxo"
            ordem = reg.get("ordem")
            crit = reg.get("criticidade") or "nao declarada"
            if crit == "essencial":
                essenciais += 1

            if f["id"] not in ids_vistos:
                ids_vistos.add(f["id"])
                nos.append(NoEvidencia(
                    label="Funcao", id=f["id"],
                    propriedades={
                        "descricao": f.get("descricao", ""),
                        "estagio": ordem if posicao == "fluxo" else "suporte",
                        "criticidade": crit,
                    },
                ))
            arestas.append(ArestaEvidencia(
                tipo="REQUER", origem_id=pid, destino_id=f["id"],
                propriedades={"ordem": ordem, "criticidade": crit, "posicao": posicao},
            ))

            rotulo = f.get("descricao", f["id"])
            if posicao == "suporte":
                suporte.append(f"{rotulo} ({crit})")
            else:
                estagios.setdefault(int(ordem or 0), []).append(rotulo)

            if a:
                if a["id"] not in ids_vistos:
                    ids_vistos.add(a["id"])
                    nos.append(NoEvidencia(
                        label="Ativo", id=a["id"],
                        propriedades={"descricao": a.get("descricao", "")},
                    ))
                arestas.append(ArestaEvidencia(
                    tipo="DESEMPENHA", origem_id=a["id"], destino_id=f["id"],
                ))

        paralelos = sum(1 for fs in estagios.values() if len(fs) > 1)
        calculos = [
            CalculoEvidencia(
                nome="estagios_no_fluxo", formula="count(distinct ordem onde posicao=fluxo)",
                valor=len(estagios), unidade="estagios",
            ),
            CalculoEvidencia(
                nome="estagios_paralelos", formula="count(estagio com mais de uma funcao)",
                valor=paralelos, unidade="estagios",
            ),
            CalculoEvidencia(
                nome="funcoes_de_suporte", formula="count(Funcao onde posicao=suporte)",
                valor=len(suporte), unidade="funcoes",
            ),
            CalculoEvidencia(
                nome="funcoes_essenciais", formula="count(REQUER onde criticidade=essencial)",
                valor=essenciais, unidade="funcoes",
            ),
        ]
        h_op = proc.get("horas_operacao_ano")
        h_cal = proc.get("horas_calendario_ano")
        if h_op and h_cal:
            calculos.append(CalculoEvidencia(
                nome="fator_exposicao",
                formula="horas_calendario_ano / horas_operacao_ano",
                valor=round(float(h_cal) / float(h_op), 3), unidade="x",
            ))

        lacunas = []
        sem_ordem = [r for r in registros if r.get("ordem") is None]
        if sem_ordem:
            lacunas.append(
                f"{len(sem_ordem)} funcao(oes) sem ordem declarada — "
                f"nao entram na sequencia.",
            )
        if not estagios:
            lacunas.append("Processo sem estagio de fluxo declarado.")

        sequencia = " -> ".join(
            (" + ".join(estagios[o]) if len(estagios[o]) > 1 else estagios[o][0])
            for o in sorted(estagios)
        ) or "nenhum estagio declarado"

        regime = proc.get("regime", "regime nao declarado")
        return EnvelopeEvidencia(
            afirmacao=(
                f"O processo {proc.get('descricao', pid)} opera em regime "
                f"{regime} e percorre {len(estagios)} estagio(s): {sequencia}. "
                f"Apoiam o fluxo {len(suporte)} funcao(oes) de suporte"
                + (f": {', '.join(suporte)}." if suporte else ".")
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
