from pydantic import BaseModel

from intents.base import (
    ArestaEvidencia,
    CalculoEvidencia,
    EnvelopeEvidencia,
    IntencaoBase,
    NoEvidencia,
    resolver_no,
)


class ImpactoFuncaoParams(BaseModel):
    funcao_id: str


class ImpactoFuncao(IntencaoBase):
    """O que acontece com os processos se esta funcao parar.

    A pergunta que o modelo antigo nao respondia. `REQUER` era uma aresta sem
    propriedade, entao perder recebimento de material e perder utilidades
    gerais eram indistinguiveis. Agora a criticidade esta declarada na relacao
    — e a criticidade e da RELACAO, nao da funcao: a mesma funcao pode ser
    essencial num processo e auxiliar em outro.

    A resposta separa PARAR de DEGRADAR: funcao essencial sem irmao paralelo
    interrompe o processo; com irmao, degrada.
    """

    nome = "impacto_funcao"
    descricao = (
        "Diz o que acontece com cada processo se uma funcao parar, separando "
        "o que interrompe do que apenas degrada"
    )

    def executar(self, session, params: ImpactoFuncaoParams) -> EnvelopeEvidencia:
        funcao = resolver_no(session, "Funcao", params.funcao_id)
        fid = funcao["id"]

        nos = [NoEvidencia(
            label="Funcao", id=fid,
            propriedades={"descricao": funcao.get("descricao", "")},
        )]
        arestas = []
        ids_vistos = {fid}

        for r in session.run(
            "MATCH (a:Ativo)-[:DESEMPENHA]->(f:Funcao {id: $fid}) RETURN a",
            parameters={"fid": fid},
        ):
            a = r["a"]
            if a["id"] not in ids_vistos:
                ids_vistos.add(a["id"])
                nos.append(NoEvidencia(
                    label="Ativo", id=a["id"],
                    propriedades={"descricao": a.get("descricao", "")},
                ))
            arestas.append(ArestaEvidencia(
                tipo="DESEMPENHA", origem_id=a["id"], destino_id=fid,
            ))

        registros = list(session.run(
            """
            MATCH (p:ProcessoOperacional)-[r:REQUER]->(f:Funcao {id: $fid})
            RETURN p AS processo, r.criticidade AS criticidade,
                   r.ordem AS ordem, r.posicao AS posicao
            ORDER BY p.id
            """,
            parameters={"fid": fid},
        ))

        interrompe, degrada, sem_efeito = [], [], []

        for reg in registros:
            p = reg["processo"]
            crit = reg.get("criticidade") or "nao declarada"
            ordem = reg.get("ordem")
            posicao = reg.get("posicao") or "fluxo"

            if p["id"] not in ids_vistos:
                ids_vistos.add(p["id"])
                nos.append(NoEvidencia(
                    label="ProcessoOperacional", id=p["id"],
                    propriedades={
                        "descricao": p.get("descricao", ""),
                        "regime": p.get("regime", ""),
                    },
                ))
            arestas.append(ArestaEvidencia(
                tipo="REQUER", origem_id=p["id"], destino_id=fid,
                propriedades={"criticidade": crit, "ordem": ordem, "posicao": posicao},
            ))

            # Irmao paralelo: outra funcao no mesmo processo, mesma ordem.
            irmaos = 0
            if posicao == "fluxo" and ordem is not None:
                reg_irmaos = session.run(
                    """
                    MATCH (p:ProcessoOperacional {id: $pid})-[r:REQUER]->(outra:Funcao)
                    WHERE r.ordem = $ordem AND outra.id <> $fid AND r.posicao = 'fluxo'
                    RETURN count(outra) AS c
                    """,
                    parameters={"pid": p["id"], "ordem": ordem, "fid": fid},
                ).single()
                irmaos = int(reg_irmaos["c"]) if reg_irmaos and reg_irmaos["c"] else 0

            desc_p = p.get("descricao", p["id"])
            if crit == "essencial" and irmaos == 0:
                interrompe.append(desc_p)
            elif crit in {"essencial", "importante"}:
                degrada.append(
                    f"{desc_p}"
                    + (f" (tem {irmaos} funcao(oes) em paralelo)" if irmaos else ""),
                )
            else:
                sem_efeito.append(desc_p)

        calculos = [
            CalculoEvidencia(
                nome="processos_que_usam", formula="count(ProcessoOperacional via REQUER)",
                valor=len(registros), unidade="processos",
            ),
            CalculoEvidencia(
                nome="processos_interrompidos",
                formula="count(processo onde criticidade=essencial e sem funcao paralela)",
                valor=len(interrompe), unidade="processos",
            ),
            CalculoEvidencia(
                nome="processos_degradados",
                formula="count(processo onde ha paralelo ou criticidade=importante)",
                valor=len(degrada), unidade="processos",
            ),
        ]

        lacunas = []
        if not registros:
            lacunas.append("Nenhum processo declara requerer esta funcao.")
        nao_declaradas = [
            r for r in registros if not r.get("criticidade")
        ]
        if nao_declaradas:
            lacunas.append(
                f"{len(nao_declaradas)} relacao(oes) sem criticidade declarada — "
                f"o efeito da perda nao e derivavel.",
            )

        desc_f = funcao.get("descricao", fid)
        partes = []
        if interrompe:
            partes.append(f"interrompe {len(interrompe)}: {', '.join(interrompe)}")
        if degrada:
            partes.append(f"degrada {len(degrada)}: {', '.join(degrada)}")
        if sem_efeito:
            partes.append(f"sem efeito imediato em {len(sem_efeito)}: {', '.join(sem_efeito)}")

        return EnvelopeEvidencia(
            afirmacao=(
                f"Se a funcao {desc_f} parar, "
                + ("; ".join(partes) if partes else "nenhum processo declarado e afetado")
                + "."
            ),
            nos=nos,
            arestas=arestas,
            calculos=calculos,
            normas=[],
            lacunas=lacunas,
        )
