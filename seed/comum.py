"""Entidades comuns aos dois setores.

Tudo aqui e dirigido pelo grafo, nao por listas de IDs: as funcoes olham o
que ja existe (Ativo, Equipamento, Defeito, ProcessoOperacional) e derivam as
entidades faltantes. Isso mantem um unico corpo de codigo para agro e
eletrico — duplicar por setor invalidaria a tese do projeto (regra 5).

Todas as funcoes sao idempotentes: usam MERGE e derivam IDs de forma
deterministica a partir dos nos existentes (regra 6).

Vocabulario setorial nunca entra (regra 3): as descricoes valem nos dois
setores. Nomes de parte de equipamento (rolamento, vedacao) nao sao jargao
setorial — sao componentes que existem em ambos.

`Material` fica deliberadamente de fora: CLAUDE.md o congela ate haver
cliente real. Por consequencia, a aresta Etapa-USA_MATERIAL->Material
permanece vazia, e isso e intencional.
"""

from seed.generator.fixtures_loader import carregar_normas

# Parte do equipamento tipicamente afetada por cada modo de falha ISO 14224.
# Serve para localizar o defeito (Defeito-IDENTIFICADO_EM->ParteObjeto).
# Só entram codigos que existem em fixtures/iso14224/modos_falha.yaml (regra 4).
# Modo sem entrada aqui simplesmente nao gera ParteObjeto — nao se inventa
# localizacao para o defeito.
PARTE_POR_MODO = {
    "VIB": ("rolamento", "Rolamento"),
    "NOI": ("rolamento", "Rolamento"),
    "ELP": ("vedacao", "Vedacao"),
    "INL": ("vedacao", "Vedacao"),
    "OHE": ("enrolamento", "Enrolamento"),
    "ERO": ("impelidor", "Impelidor"),
    "BRD": ("eixo", "Eixo"),
    "UST": ("estrutura", "Estrutura"),
    "SHC": ("isolacao", "Isolacao"),
    "FTS": ("atuador", "Atuador"),
    "FTO": ("atuador", "Atuador"),
    "FTC": ("atuador", "Atuador"),
}

# Consequencia registrada na nota, por tipo de nota.
CONSEQUENCIAS = [
    {"id": "CNS-PAR", "descricao": "Parada de producao", "severidade": "alta"},
    {"id": "CNS-DEG", "descricao": "Degradacao de desempenho", "severidade": "media"},
    {"id": "CNS-SEG", "descricao": "Risco de seguranca", "severidade": "alta"},
    {"id": "CNS-NIL", "descricao": "Sem impacto imediato", "severidade": "baixa"},
]

# Etapas padrao de uma ordem de manutencao.
ETAPAS_PADRAO = [
    {"sufixo": "01", "descricao": "Bloqueio e sinalizacao de energia", "ordem": 1},
    {"sufixo": "02", "descricao": "Diagnostico e desmontagem", "ordem": 2},
    {"sufixo": "03", "descricao": "Intervencao corretiva", "ordem": 3},
    {"sufixo": "04", "descricao": "Teste funcional e liberacao", "ordem": 4},
]


def criar_normas_e_requisitos(session, normas: list[dict]) -> int:
    """Cria Norma e seus Requisito (Norma-TEM_REQUISITO->Requisito)."""
    total = 0
    for n in normas:
        session.run(
            "MERGE (n:Norma {id: $id}) SET n.codigo = $codigo, n.descricao = $descricao",
            parameters={"id": n["id"], "codigo": n["codigo"], "descricao": n["descricao"]},
        )
        for r in n.get("requisitos", []):
            session.run(
                """
                MERGE (rq:Requisito {id: $rid})
                SET rq.descricao = $desc, rq.criticidade = $crit
                WITH rq
                MATCH (n:Norma {id: $nid})
                MERGE (n)-[:TEM_REQUISITO]->(rq)
                """,
                parameters={
                    "rid": r["id"], "desc": r["descricao"],
                    "crit": r.get("criticidade", "media"), "nid": n["id"],
                },
            )
            total += 1
    return total


def criar_partes_objeto(session) -> int:
    """Cria ParteObjeto para equipamentos que tem defeito, e localiza o defeito.

    ParteObjeto-PERTENCE->Equipamento e Defeito-IDENTIFICADO_EM->ParteObjeto.
    A parte e derivada do modo de falha declarado no defeito, entao nao ha
    invencao: se o modo nao estiver no mapa, a parte nao e criada.
    """
    registros = list(session.run(
        """
        MATCH (d:Defeito)-[:DETECTADO_EM]->(eq:Equipamento)
        MATCH (d)-[:MANIFESTOU]->(mf:ModoFalha)
        RETURN d.id AS did, eq.id AS eqid, mf.id AS modo
        """,
    ))

    total = 0
    for r in registros:
        chave = PARTE_POR_MODO.get(r["modo"])
        if chave is None:
            continue
        slug, descricao = chave
        parte_id = f"PO-{r['eqid']}-{slug.upper()[:3]}"
        session.run(
            """
            MERGE (p:ParteObjeto {id: $pid})
            SET p.descricao = $desc
            WITH p
            MATCH (eq:Equipamento {id: $eqid})
            MERGE (p)-[:PERTENCE]->(eq)
            WITH p
            MATCH (d:Defeito {id: $did})
            MERGE (d)-[:IDENTIFICADO_EM]->(p)
            """,
            parameters={"pid": parte_id, "desc": descricao, "eqid": r["eqid"], "did": r["did"]},
        )
        total += 1
    return total


def criar_planos_manutencao(session) -> int:
    """Cria um PlanoManutencao por Ativo, com ListaTarefa associada.

    PlanoManutencao-COBRE->Ativo e PlanoManutencao-USA_LISTA->ListaTarefa.
    """
    ativos = list(session.run("MATCH (a:Ativo) RETURN a.id AS id, a.descricao AS desc"))

    for a in ativos:
        plano_id = f"PM-{a['id']}"
        lista_id = f"LT-{a['id']}"
        session.run(
            """
            MERGE (pm:PlanoManutencao {id: $pmid})
            SET pm.descricao = $pmdesc, pm.periodicidade_dias = $per
            MERGE (lt:ListaTarefa {id: $ltid})
            SET lt.descricao = $ltdesc
            MERGE (pm)-[:USA_LISTA]->(lt)
            WITH pm
            MATCH (a:Ativo {id: $aid})
            MERGE (pm)-[:COBRE]->(a)
            """,
            parameters={
                "pmid": plano_id,
                "pmdesc": f"Plano preventivo — {a['desc']}",
                "per": 90,
                "ltid": lista_id,
                "ltdesc": f"Lista de tarefas preventivas — {a['desc']}",
                "aid": a["id"],
            },
        )

    # Vincula ao plano as ordens preventivas ja existentes no ativo.
    session.run(
        """
        MATCH (pm:PlanoManutencao)-[:COBRE]->(a:Ativo)
        MATCH (om:OrdemManutencao)-[:ATRIBUIDA]->(a)
        WHERE om.tipo = 'preventiva'
        MERGE (pm)-[:GEROU_ORDEM]->(om)
        """,
    )
    return len(ativos)


def criar_indicadores(session) -> int:
    """Cria Indicador medindo cada ProcessoOperacional (Indicador-MEDE->Processo)."""
    processos = list(session.run(
        "MATCH (p:ProcessoOperacional) RETURN p.id AS id, p.descricao AS desc",
    ))

    modelos = [
        ("DISP", "Disponibilidade operacional", "%", 95.0),
        ("MTBF", "Tempo medio entre falhas", "horas", 1200.0),
    ]

    total = 0
    for p in processos:
        for sufixo, desc, unidade, meta in modelos:
            session.run(
                """
                MERGE (i:Indicador {id: $iid})
                SET i.descricao = $desc, i.unidade = $un, i.meta = $meta
                WITH i
                MATCH (p:ProcessoOperacional {id: $pid})
                MERGE (i)-[:MEDE]->(p)
                """,
                parameters={
                    "iid": f"IND-{p['id']}-{sufixo}", "desc": desc,
                    "un": unidade, "meta": meta, "pid": p["id"],
                },
            )
            total += 1
    return total


def criar_consequencias_nota(session) -> int:
    """Cria ConsequenciaNota e atrela as notas (Nota-ATRELADA->Consequencia).

    A consequencia e derivada do tipo da nota, nao sorteada: nota corretiva
    para de producao, preventiva nao tem impacto imediato.
    """
    for c in CONSEQUENCIAS:
        session.run(
            "MERGE (c:ConsequenciaNota {id: $id}) SET c.descricao = $descricao, "
            "c.severidade = $severidade",
            parameters=c,
        )

    # Nota preventiva nao tem impacto imediato — foi planejada.
    total = 0
    r = session.run(
        """
        MATCH (nm:NotaManutencao), (c:ConsequenciaNota {id: 'CNS-NIL'})
        WHERE nm.tipo = 'preventiva'
        MERGE (nm)-[:ATRELADA]->(c)
        RETURN count(nm) AS c
        """,
    ).single()
    total += r["c"] if r else 0

    # Nota corretiva: a consequencia sai do modo de falha do evento que a
    # originou, nao do tipo da nota. Modo que tira o item de servico para a
    # producao; modo de seguranca vira risco; o resto e degradacao. Assim a
    # distribuicao reflete o que aconteceu, em vez de rotular tudo igual.
    for modos, cns in [
        (["FTS", "FTO", "FTC", "BRD", "UST"], "CNS-PAR"),
        (["SHC", "OHE"], "CNS-SEG"),
    ]:
        r = session.run(
            """
            MATCH (ev:EventoFalha)-[:GEROU]->(nm:NotaManutencao)
            MATCH (ev)-[:MANIFESTOU]->(mf:ModoFalha)
            MATCH (c:ConsequenciaNota {id: $cid})
            WHERE nm.tipo = 'corretiva' AND mf.id IN $modos
            MERGE (nm)-[:ATRELADA]->(c)
            RETURN count(nm) AS c
            """,
            parameters={"modos": modos, "cid": cns},
        ).single()
        total += r["c"] if r else 0

    # Corretiva que sobrou (inclusive sem evento associado) e degradacao.
    r = session.run(
        """
        MATCH (nm:NotaManutencao), (c:ConsequenciaNota {id: 'CNS-DEG'})
        WHERE nm.tipo = 'corretiva' AND NOT (nm)-[:ATRELADA]->(:ConsequenciaNota)
        MERGE (nm)-[:ATRELADA]->(c)
        RETURN count(nm) AS c
        """,
    ).single()
    total += r["c"] if r else 0
    return total


def ligar_organizacao(session) -> None:
    """Liga organizacao e regulacao, depois que todos os nos existem.

    Equipamento-MANTIDO_POR->CentroTrabalho, *-PLANEJADO_POR->GrupoPlanejamento
    e ClasseTaxonomia-REGULADO_POR->Norma.

    A ligacao das classes com as normas vive aqui, e nao junto da criacao
    das normas, porque naquele ponto do seeder a taxonomia ainda nao existe:
    o MERGE casava com zero nos na primeira passada e so aparecia na segunda,
    quebrando a idempotencia (regra 6) e deixando `normas_aplicaveis` sem
    dado num banco recem-semeado.

    A quais classes cada norma se aplica esta declarado em
    fixtures/normas.yaml (`classes_aplicaveis`), nao embutido aqui — e um
    julgamento de engenharia, e como tal precisa ficar num lugar revisavel.
    """
    for norma in carregar_normas():
        aplicaveis = norma.get("classes_aplicaveis")
        if aplicaveis == "*":
            session.run(
                """
                MATCH (ct:ClasseTaxonomia), (n:Norma {id: $nid})
                MERGE (ct)-[:REGULADO_POR]->(n)
                """,
                parameters={"nid": norma["id"]},
            )
        elif aplicaveis:
            session.run(
                """
                MATCH (ct:ClasseTaxonomia), (n:Norma {id: $nid})
                WHERE ct.id IN $classes
                MERGE (ct)-[:REGULADO_POR]->(n)
                """,
                parameters={"nid": norma["id"], "classes": list(aplicaveis)},
            )
    session.run(
        """
        MATCH (eq:Equipamento), (ct:CentroTrabalho)
        MERGE (eq)-[:MANTIDO_POR]->(ct)
        """,
    )
    for label in ["Ativo", "Sistema", "Edificacao", "Equipamento"]:
        session.run(
            f"""
            MATCH (x:{label}), (gp:GrupoPlanejamento)
            MERGE (x)-[:PLANEJADO_POR]->(gp)
            """,
        )


def criar_etapas_das_ordens(session) -> int:
    """Cria Etapa para um subconjunto estavel de ordens corretivas.

    OrdemManutencao-TEM_ETAPA->Etapa e Etapa-EXECUTADA_POR->Equipe.

    Nao se criam etapas em todas as ordens: 4 etapas em 233 ordens inflaria o
    grafo sem acrescentar nada a demo. A selecao precisa ser um PREDICADO, nao
    uma janela do tipo `ORDER BY ... LIMIT n` — uma janela desliza quando
    ordens novas aparecem depois (OM-DEF-901 ordena acima de OM-0231), e o
    seeder deixa de ser idempotente na segunda passada.

    Sao escolhidas:
    - todas as ordens que resolvem um Defeito — as que a demo mostra;
    - as demais corretivas cujo id termina em '0' — amostra deterministica,
      estavel independente de ordem de insercao.
    """
    ordens = list(session.run(
        """
        MATCH (om:OrdemManutencao)
        WHERE om.tipo = 'corretiva'
          AND ( (om)-[:RESOLVE]->(:Defeito) OR om.id ENDS WITH '0' )
        RETURN om.id AS id
        """,
    ))

    total = 0
    for o in ordens:
        for e in ETAPAS_PADRAO:
            session.run(
                """
                MERGE (et:Etapa {id: $eid})
                SET et.descricao = $desc, et.ordem = $ord
                WITH et
                MATCH (om:OrdemManutencao {id: $oid})
                MERGE (om)-[:TEM_ETAPA]->(et)
                WITH et
                MATCH (eqp:Equipe)
                MERGE (et)-[:EXECUTADA_POR]->(eqp)
                """,
                parameters={
                    "eid": f"ETP-{o['id']}-{e['sufixo']}",
                    "desc": e["descricao"], "ord": e["ordem"], "oid": o["id"],
                },
            )
            total += 1
    return total


def criar_defeitos_resolvidos(session, defeitos: list[dict]) -> int:
    """Cria defeitos ja encerrados, com a cadeia de falha completa.

    Os defeitos abertos do seeder nao tem evento, nota nem acao tomada — o
    que esta semanticamente certo, mas deixa `cadeia_falha` sem nada para
    mostrar. Estes aqui fecham o ciclo:

        Defeito -EVOLUIU_PARA-> EventoFalha
        Defeito -GEROU-> NotaManutencao -GEROU_ORDEM-> OrdemManutencao
        Defeito -RESOLVIDO_POR-> AcaoTomada

    Assim a demo mostra os dois casos: um defeito aberto, com lacunas
    honestas, e um encerrado, com a cadeia inteira.
    """
    for d in defeitos:
        session.run(
            """
            MERGE (d:Defeito {id: $did})
            SET d.descricao = $desc, d.status = 'resolvido',
                d.data_deteccao_horas = $hdet, d.data_encerramento_horas = $henc
            WITH d
            MATCH (eq:Equipamento {id: $eqid})
            MERGE (d)-[:DETECTADO_EM]->(eq)
            WITH d
            MATCH (mf:ModoFalha {id: $modo})
            MERGE (d)-[:MANIFESTOU]->(mf)
            WITH d
            MATCH (cf:CausaFalha {id: $causa})
            MERGE (d)-[:CAUSADO_POR]->(cf)
            WITH d
            MATCH (mec:MecanismoFalha {id: $mecanismo})
            MERGE (d)-[:VIA_MECANISMO]->(mec)
            """,
            parameters={
                "did": d["id"], "desc": d["descricao"], "eqid": d["equipamento"],
                "modo": d["modo"], "causa": d["causa"], "mecanismo": d["mecanismo"],
                "hdet": d["horas_deteccao"], "henc": d["horas_encerramento"],
            },
        )

        evento_id = f"EV-{d['id']}"
        nota_id = f"NM-{d['id']}"
        ordem_id = f"OM-{d['id']}"
        acao_id = f"AT-{d['id']}"

        session.run(
            """
            MATCH (d:Defeito {id: $did})
            MATCH (eq:Equipamento {id: $eqid})
            MERGE (ev:EventoFalha {id: $evid})
            SET ev.timestamp_horas_operacao = $henc, ev.ano = $ano
            MERGE (d)-[:EVOLUIU_PARA]->(ev)
            MERGE (ev)-[:OCORREU]->(eq)
            """,
            parameters={
                "did": d["id"], "eqid": d["equipamento"], "evid": evento_id,
                "henc": d["horas_encerramento"], "ano": d["ano"],
            },
        )

        session.run(
            """
            MATCH (d:Defeito {id: $did})
            MATCH (eq:Equipamento {id: $eqid})
            MERGE (nm:NotaManutencao {id: $nmid})
            SET nm.descricao = $nmdesc, nm.tipo = 'corretiva'
            MERGE (d)-[:GEROU]->(nm)
            MERGE (nm)-[:ATRIBUIDA]->(eq)
            MERGE (om:OrdemManutencao {id: $omid})
            SET om.descricao = $omdesc, om.tipo = 'corretiva'
            MERGE (nm)-[:GEROU_ORDEM]->(om)
            MERGE (om)-[:EXECUTADA_EM]->(eq)
            MERGE (om)-[:RESOLVE]->(d)
            """,
            parameters={
                "did": d["id"], "eqid": d["equipamento"], "nmid": nota_id,
                "nmdesc": f"Nota corretiva — {d['descricao']}",
                "omid": ordem_id, "omdesc": f"Ordem corretiva — {d['descricao']}",
            },
        )

        session.run(
            """
            MATCH (d:Defeito {id: $did})
            MERGE (at:AcaoTomada {id: $atid})
            SET at.descricao = $atdesc, at.horas_execucao = $horas
            MERGE (d)-[:RESOLVIDO_POR]->(at)
            """,
            parameters={
                "did": d["id"], "atid": acao_id,
                "atdesc": d["acao_tomada"], "horas": d["horas_execucao"],
            },
        )

    return len(defeitos)
