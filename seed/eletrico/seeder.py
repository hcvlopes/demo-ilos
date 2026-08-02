"""Seeder do setor eletrico — subestacao de distribuicao.

Popula o grafo com dados sinteticos de uma subestacao de
distribuicao de energia, usando perfil uniforme de operacao (24/7)
e lambda de referencia ISO 14224.

Idempotente: usa MERGE em todos os nos. Rodar duas vezes produz o mesmo grafo.
Deterministico: semente fixa para reprodutibilidade.

Prova a tese: o mesmo schema, as mesmas intencoes e o mesmo motor de risco
funcionam para um setor diferente — o vocabulario setorial resolve na renderizacao.
"""

import importlib
from collections import defaultdict

import numpy as np
from db.adapter import create_driver
from seed import comum
from seed.generator.estimador import estimar_lambda
from seed.generator.fixtures_loader import (
    carregar_acoes_permitidas,
    carregar_causas_falha,
    carregar_classes_taxonomia,
    carregar_lambda_verdadeiro,
    carregar_mecanismos_falha,
    carregar_modos_falha,
    carregar_normas,
)
from seed.generator.poisson import PERFIL_UNIFORME, gerar_historico

SEED = 7
N_MESES = 24

PAPEIS = [
    {"id": "PAPEL-ENG", "descricao": "Engenheiro de confiabilidade", "nivel": "senior"},
    {"id": "PAPEL-SUP", "descricao": "Supervisor de manutencao", "nivel": "pleno"},
    {"id": "PAPEL-TEC", "descricao": "Tecnico de manutencao", "nivel": "operacional"},
]

VIABILIDADE_POR_COMPLEXIDADE = {
    "baixa": 0.9,
    "media": 0.6,
    "alta": 0.3,
}

AUTORIZACAO_POR_COMPLEXIDADE = {
    "baixa": ["PAPEL-TEC", "PAPEL-SUP", "PAPEL-ENG"],
    "media": ["PAPEL-SUP", "PAPEL-ENG"],
    "alta": ["PAPEL-ENG"],
}

EDIFICACAO = {
    "id": "EDIF-002",
    "descricao": "Subestacao regional 01",
}

SISTEMAS = [
    {"id": "SIS-TRN", "descricao": "Transformacao"},
    {"id": "SIS-PRO", "descricao": "Protecao"},
    {"id": "SIS-DST", "descricao": "Distribuicao"},
    {"id": "SIS-CTR", "descricao": "Controle e automacao"},
    {"id": "SIS-AXL", "descricao": "Servicos auxiliares"},
]

ATIVOS = [
    {"id": "ATV-TRN-01", "descricao": "Bay de transformacao 01", "sistema": "SIS-TRN"},
    {"id": "ATV-TRN-02", "descricao": "Bay de transformacao 02", "sistema": "SIS-TRN"},
    {"id": "ATV-PRO-01", "descricao": "Modulo de protecao 01", "sistema": "SIS-PRO"},
    {"id": "ATV-DST-01", "descricao": "Alimentador 01", "sistema": "SIS-DST"},
    {"id": "ATV-DST-02", "descricao": "Alimentador 02", "sistema": "SIS-DST"},
    {"id": "ATV-CTR-01", "descricao": "Painel de controle", "sistema": "SIS-CTR"},
    {"id": "ATV-AXL-01", "descricao": "Grupo auxiliar", "sistema": "SIS-AXL"},
]

EQUIPAMENTOS = [
    # Transformação 01
    {"id": "EQ-TRF-101", "descricao": "Transformador principal 01", "classe": "CT-TRF", "ativo": "ATV-TRN-01"},
    {"id": "EQ-DJT-101", "descricao": "Disjuntor AT bay 01", "classe": "CT-DJT", "ativo": "ATV-TRN-01"},
    {"id": "EQ-TCL-101", "descricao": "Trocador calor TRF-01", "classe": "CT-TCL", "ativo": "ATV-TRN-01"},
    {"id": "EQ-BCC-101", "descricao": "Bomba circulacao TRF-01", "classe": "CT-BCC", "ativo": "ATV-TRN-01"},
    {"id": "EQ-MOE-101", "descricao": "Motor ventilador TRF-01", "classe": "CT-MOE", "ativo": "ATV-TRN-01"},
    # Transformação 02
    {"id": "EQ-TRF-102", "descricao": "Transformador principal 02", "classe": "CT-TRF", "ativo": "ATV-TRN-02"},
    {"id": "EQ-DJT-102", "descricao": "Disjuntor AT bay 02", "classe": "CT-DJT", "ativo": "ATV-TRN-02"},
    {"id": "EQ-TCL-102", "descricao": "Trocador calor TRF-02", "classe": "CT-TCL", "ativo": "ATV-TRN-02"},
    {"id": "EQ-MOE-102", "descricao": "Motor ventilador TRF-02", "classe": "CT-MOE", "ativo": "ATV-TRN-02"},
    # Proteção
    {"id": "EQ-DJT-103", "descricao": "Disjuntor seccionador 01", "classe": "CT-DJT", "ativo": "ATV-PRO-01"},
    {"id": "EQ-DJT-104", "descricao": "Disjuntor seccionador 02", "classe": "CT-DJT", "ativo": "ATV-PRO-01"},
    {"id": "EQ-VSG-101", "descricao": "Valvula seguranca SF6", "classe": "CT-VSG", "ativo": "ATV-PRO-01"},
    # Distribuição — alimentador 01
    {"id": "EQ-DJT-105", "descricao": "Disjuntor alimentador 01", "classe": "CT-DJT", "ativo": "ATV-DST-01"},
    {"id": "EQ-VCT-101", "descricao": "Chave seccionadora 01", "classe": "CT-VCT", "ativo": "ATV-DST-01"},
    {"id": "EQ-TRE-101", "descricao": "Barramento 01", "classe": "CT-TRE", "ativo": "ATV-DST-01"},
    # Distribuição — alimentador 02
    {"id": "EQ-DJT-106", "descricao": "Disjuntor alimentador 02", "classe": "CT-DJT", "ativo": "ATV-DST-02"},
    {"id": "EQ-VCT-102", "descricao": "Chave seccionadora 02", "classe": "CT-VCT", "ativo": "ATV-DST-02"},
    # Controle
    {"id": "EQ-MOE-103", "descricao": "Motor UPS controle", "classe": "CT-MOE", "ativo": "ATV-CTR-01"},
    # Auxiliar
    {"id": "EQ-GER-101", "descricao": "Gerador diesel auxiliar", "classe": "CT-GER", "ativo": "ATV-AXL-01"},
    {"id": "EQ-CMP-101", "descricao": "Compressor ar servico", "classe": "CT-CMP", "ativo": "ATV-AXL-01"},
    {"id": "EQ-BCP-101", "descricao": "Bomba oleo auxiliar", "classe": "CT-BCP", "ativo": "ATV-AXL-01"},
]

NORMAS = [
    {"id": "NORMA-ISO14224", "codigo": "ISO 14224:2016", "descricao": "Coleta e intercambio de dados de confiabilidade"},
    {"id": "NORMA-NR10", "codigo": "NR-10", "descricao": "Seguranca em instalacoes e servicos em eletricidade"},
]

FABRICANTES = [
    {"id": "FAB-101", "nome": "Fabricante Delta", "pais": "BR"},
    {"id": "FAB-102", "nome": "Fabricante Epsilon", "pais": "DE"},
]

CENTRO_TRABALHO = {"id": "CT-MNT-002", "descricao": "Centro de manutencao eletrica"}
EQUIPE = {"id": "EQP-002", "descricao": "Equipe de manutencao eletrica"}

FUNCOES = [
    {"id": "FUN-TRN-01", "descricao": "Transformacao 01", "ativo": "ATV-TRN-01"},
    {"id": "FUN-TRN-02", "descricao": "Transformacao 02", "ativo": "ATV-TRN-02"},
    {"id": "FUN-PRO", "descricao": "Protecao", "ativo": "ATV-PRO-01"},
    {"id": "FUN-DST-01", "descricao": "Distribuicao 01", "ativo": "ATV-DST-01"},
    {"id": "FUN-DST-02", "descricao": "Distribuicao 02", "ativo": "ATV-DST-02"},
    {"id": "FUN-CTR", "descricao": "Controle e supervisao", "ativo": "ATV-CTR-01"},
    {"id": "FUN-AXL", "descricao": "Servicos auxiliares", "ativo": "ATV-AXL-01"},
]

PROCESSO = {"id": "PO-002", "descricao": "Transformacao e distribuicao de energia"}
ENTREGA = {"id": "ENT-002", "descricao": "Continuidade do fornecimento"}
CONTRATO = {"id": "CON-002", "descricao": "Contrato de concessao"}

ALIMENTA = [
    ("ATV-TRN-01", "ATV-DST-01"),
    ("ATV-TRN-01", "ATV-DST-02"),
    ("ATV-TRN-02", "ATV-DST-01"),
    ("ATV-TRN-02", "ATV-DST-02"),
    ("ATV-AXL-01", "ATV-CTR-01"),
]

REDUNDA_COM = [
    ("ATV-TRN-01", "ATV-TRN-02", 1.0),
    ("ATV-DST-01", "ATV-DST-02", 0.5),
]

DEFEITOS = [
    {
        "id": "DEF-101",
        "descricao": "Aquecimento anormal em enrolamento",
        "equipamento": "EQ-TRF-101",
        "modo": "OHE",
        "causa": "AGE",
        "mecanismo": "OVH",
        "status": "aberto",
    },
    {
        "id": "DEF-102",
        "descricao": "Operacao espuria",
        "equipamento": "EQ-DJT-103",
        "modo": "UST",
        "causa": "OPE",
        "mecanismo": "OVH",
        "status": "aberto",
    },
    {
        "id": "DEF-103",
        "descricao": "Vazamento de oleo",
        "equipamento": "EQ-TCL-101",
        "modo": "ELP",
        "causa": "AGE",
        "mecanismo": "LEA",
        "status": "aberto",
    },
]

# Defeitos ja encerrados, com cadeia de falha completa. Os defeitos abertos
# acima nao tem evento, nota nem acao tomada — correto do ponto de vista
# semantico, mas deixa `cadeia_falha` sem nada para mostrar.
DEFEITOS_RESOLVIDOS = [
    {
        "id": "DEF-911",
        "descricao": "Falha de atuacao em disjuntor de bay",
        "equipamento": "EQ-DJT-102",
        "modo": "FTO", "causa": "MNT", "mecanismo": "STK",
        "horas_deteccao": 12400, "horas_encerramento": 12470, "ano": 2,
        "acao_tomada": "Revisao do mecanismo de operacao e lubrificacao",
        "horas_execucao": 5.0,
    },
    {
        "id": "DEF-912",
        "descricao": "Curto entre espiras em enrolamento",
        "equipamento": "EQ-TRF-102",
        "modo": "SHC", "causa": "AGE", "mecanismo": "SHC",
        "horas_deteccao": 15800, "horas_encerramento": 16040, "ano": 2,
        "acao_tomada": "Rebobinamento e ensaio de isolacao",
        "horas_execucao": 48.0,
    },
]


def _equipamentos_por_classe() -> dict[str, list[dict]]:
    por_classe: dict[str, list[dict]] = defaultdict(list)
    for eq in EQUIPAMENTOS:
        por_classe[eq["classe"]].append(eq)
    return dict(por_classe)


def _modos_para_classe(modos: list[dict], classe_id: str) -> list[dict]:
    return [m for m in modos if classe_id in m.get("aplicavel_a", [])]


def _criar_hierarquia(session) -> None:
    session.run(
        "MERGE (e:Edificacao {id: $id}) SET e.descricao = $descricao",
        EDIFICACAO,
    )
    for sis in SISTEMAS:
        session.run(
            "MERGE (s:Sistema {id: $id}) SET s.descricao = $descricao",
            sis,
        )
        session.run(
            "MATCH (e:Edificacao {id: $edif_id}), (s:Sistema {id: $sis_id}) "
            "MERGE (e)-[:CONTEM]->(s)",
            {"edif_id": EDIFICACAO["id"], "sis_id": sis["id"]},
        )
    for atv in ATIVOS:
        session.run(
            "MERGE (a:Ativo {id: $id}) SET a.descricao = $descricao",
            {"id": atv["id"], "descricao": atv["descricao"]},
        )
        session.run(
            "MATCH (s:Sistema {id: $sis_id}), (a:Ativo {id: $atv_id}) "
            "MERGE (s)-[:CONTEM]->(a)",
            {"sis_id": atv["sistema"], "atv_id": atv["id"]},
        )


def _criar_taxonomia(session, classes: list[dict]) -> None:
    for c in classes:
        session.run(
            "MERGE (ct:ClasseTaxonomia {id: $id}) "
            "SET ct.descricao = $descricao, ct.lambda_ref_1e6h = $lambda_ref",
            {"id": c["classe_id"], "descricao": c["descricao"], "lambda_ref": c["lambda_ref_1e6h"]},
        )


def _criar_modos_causas_mecanismos(session, modos, causas, mecanismos) -> None:
    for m in modos:
        session.run("MERGE (mf:ModoFalha {id: $id}) SET mf.descricao = $descricao", {"id": m["codigo"], "descricao": m["descricao"]})
    for c in causas:
        session.run("MERGE (cf:CausaFalha {id: $id}) SET cf.descricao = $descricao", {"id": c["codigo"], "descricao": c["descricao"]})
    for mec in mecanismos:
        session.run("MERGE (mec:MecanismoFalha {id: $id}) SET mec.descricao = $descricao", {"id": mec["codigo"], "descricao": mec["descricao"]})


def _criar_equipamentos(session, fabricantes_ids, rng) -> None:
    for eq in EQUIPAMENTOS:
        fab_id = rng.choice(fabricantes_ids)
        session.run(
            "MERGE (eq:Equipamento {id: $id}) SET eq.descricao = $descricao, eq.tag = $id",
            {"id": eq["id"], "descricao": eq["descricao"]},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (a:Ativo {id: $atv_id}) MERGE (eq)-[:PERTENCE]->(a)",
            {"eq_id": eq["id"], "atv_id": eq["ativo"]},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (ct:ClasseTaxonomia {id: $ct_id}) MERGE (eq)-[:CLASSIFICADO_COMO]->(ct)",
            {"eq_id": eq["id"], "ct_id": eq["classe"]},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (f:Fabricante {id: $fab_id}) MERGE (eq)-[:FABRICADO]->(f)",
            {"eq_id": eq["id"], "fab_id": fab_id},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (ct:CentroTrabalho {id: $ct_id}) MERGE (eq)-[:MANTIDO_POR]->(ct)",
            {"eq_id": eq["id"], "ct_id": CENTRO_TRABALHO["id"]},
        )


def _criar_normas_e_organizacao(session) -> None:
    for n in NORMAS:
        session.run("MERGE (n:Norma {id: $id}) SET n.codigo = $codigo, n.descricao = $descricao", n)
    for f in FABRICANTES:
        session.run("MERGE (f:Fabricante {id: $id}) SET f.nome = $nome, f.pais = $pais", f)
    session.run("MERGE (ct:CentroTrabalho {id: $id}) SET ct.descricao = $descricao", CENTRO_TRABALHO)
    session.run("MERGE (eq:Equipe {id: $id}) SET eq.descricao = $descricao", EQUIPE)
    # A ligacao ClasseTaxonomia-REGULADO_POR->Norma roda em
    # comum.ligar_organizacao(), depois que a taxonomia existe.


def _gerar_e_criar_eventos(session, lambdas, modos, causas, mecanismos, rng) -> dict[str, list]:
    eq_por_classe = _equipamentos_por_classe()
    historicos_por_classe: dict[str, list] = defaultdict(list)
    evento_counter = 5000
    nota_counter = 5000
    ordem_counter = 5000

    causas_ids = [c["codigo"] for c in causas]
    mecanismos_ids = [m["codigo"] for m in mecanismos]

    for classe_id, lambda_v in lambdas.items():
        eqs = eq_por_classe.get(classe_id, [])
        if not eqs:
            continue
        modos_aplicaveis = _modos_para_classe(modos, classe_id)
        if not modos_aplicaveis:
            modos_aplicaveis = [{"codigo": "OTH"}]
        modos_ids = [m["codigo"] for m in modos_aplicaveis]

        for eq in eqs:
            historico = gerar_historico(
                classe_id=classe_id,
                lambda_por_hora_op=lambda_v,
                n_meses=N_MESES,
                perfil=PERFIL_UNIFORME,
                rng=rng,
                n_equipamentos=1,
            )
            historicos_por_classe[classe_id].append(historico)

            for evento in historico.eventos:
                evento_counter += 1
                nota_counter += 1
                ordem_counter += 1
                ev_id = f"EF-{evento_counter:04d}"
                nota_id = f"NM-{nota_counter:04d}"
                ordem_id = f"OM-{ordem_counter:04d}"
                modo_id = rng.choice(modos_ids)
                causa_id = rng.choice(causas_ids)
                mec_id = rng.choice(mecanismos_ids)

                session.run(
                    "MERGE (ef:EventoFalha {id: $id}) "
                    "SET ef.timestamp_horas_operacao = $ts_hop, ef.ano = $ano, ef.mes = $mes, ef.hora_calendario = $hora_cal",
                    {"id": ev_id, "ts_hop": evento.timestamp_horas_operacao, "ano": evento.ano, "mes": evento.mes, "hora_cal": evento.hora_calendario},
                )
                session.run("MATCH (ef:EventoFalha {id: $ef_id}), (eq:Equipamento {id: $eq_id}) MERGE (ef)-[:OCORREU]->(eq)", {"ef_id": ev_id, "eq_id": eq["id"]})
                session.run("MATCH (ef:EventoFalha {id: $ef_id}), (mf:ModoFalha {id: $mf_id}) MERGE (ef)-[:MANIFESTOU]->(mf)", {"ef_id": ev_id, "mf_id": modo_id})
                session.run("MATCH (ef:EventoFalha {id: $ef_id}), (cf:CausaFalha {id: $cf_id}) MERGE (ef)-[:CAUSADO_POR]->(cf)", {"ef_id": ev_id, "cf_id": causa_id})
                session.run("MATCH (ef:EventoFalha {id: $ef_id}), (mec:MecanismoFalha {id: $mec_id}) MERGE (ef)-[:VIA_MECANISMO]->(mec)", {"ef_id": ev_id, "mec_id": mec_id})

                session.run("MERGE (nm:NotaManutencao {id: $id}) SET nm.descricao = $d, nm.tipo = 'corretiva'", {"id": nota_id, "d": f"Nota referente a {ev_id}"})
                session.run("MATCH (ef:EventoFalha {id: $ef_id}), (nm:NotaManutencao {id: $nm_id}) MERGE (ef)-[:GEROU]->(nm)", {"ef_id": ev_id, "nm_id": nota_id})
                session.run("MATCH (nm:NotaManutencao {id: $nm_id}), (eq:Equipamento {id: $eq_id}) MERGE (nm)-[:ATRIBUIDA]->(eq)", {"nm_id": nota_id, "eq_id": eq["id"]})
                session.run("MATCH (nm:NotaManutencao {id: $nm_id}), (ct:CentroTrabalho {id: $ct_id}) MERGE (nm)-[:EXECUTADA_CT]->(ct)", {"nm_id": nota_id, "ct_id": CENTRO_TRABALHO["id"]})

                session.run("MERGE (om:OrdemManutencao {id: $id}) SET om.descricao = $d, om.tipo = 'corretiva'", {"id": ordem_id, "d": f"Ordem referente a {nota_id}"})
                session.run("MATCH (nm:NotaManutencao {id: $nm_id}), (om:OrdemManutencao {id: $om_id}) MERGE (nm)-[:GEROU_ORDEM]->(om)", {"nm_id": nota_id, "om_id": ordem_id})
                session.run("MATCH (om:OrdemManutencao {id: $om_id}), (eq:Equipamento {id: $eq_id}) MERGE (om)-[:EXECUTADA_EM]->(eq)", {"om_id": ordem_id, "eq_id": eq["id"]})
                session.run("MATCH (om:OrdemManutencao {id: $om_id}), (ef:EventoFalha {id: $ef_id}) MERGE (om)-[:RESOLVE]->(ef)", {"om_id": ordem_id, "ef_id": ev_id})

    total = evento_counter - 5000
    print(f"  {total} eventos de falha criados.")
    return dict(historicos_por_classe)


def _criar_metricas(session, historicos_por_classe) -> None:
    from seed.generator.poisson import HistoricoGerado

    for classe_id, historicos in historicos_por_classe.items():
        n_total = sum(len(h.eventos) for h in historicos)
        hop_total = sum(h.horas_operacao_total for h in historicos)
        if hop_total <= 0:
            continue

        agregado = HistoricoGerado(
            classe_id=classe_id,
            lambda_verdadeiro=0.0,
            horas_operacao_total=hop_total,
            horas_calendario_total=sum(h.horas_calendario_total for h in historicos),
            meses=N_MESES,
        )
        for h in historicos:
            agregado.eventos.extend(h.eventos)

        est = estimar_lambda(agregado)
        metrica_id = f"MC-EL-{classe_id}"
        session.run(
            "MERGE (mc:MetricaConfiabilidade {id: $id}) "
            "SET mc.lambda_hat = $lh, mc.ic_inferior = $ii, mc.ic_superior = $is, "
            "    mc.n_eventos = $ne, mc.horas_operacao = $hop, mc.nivel_confianca = $nc, mc.metodo = 'MLE_chi2'",
            {"id": metrica_id, "lh": est.lambda_hat, "ii": est.ic_inferior, "is": est.ic_superior, "ne": est.n_eventos, "hop": est.horas_operacao, "nc": est.nivel_confianca},
        )
        session.run(
            "MATCH (ct:ClasseTaxonomia {id: $ct_id}), (mc:MetricaConfiabilidade {id: $mc_id}) MERGE (ct)-[:TEM_METRICA]->(mc)",
            {"ct_id": classe_id, "mc_id": metrica_id},
        )


def _criar_funcoes_e_processos(session) -> None:
    for fun in FUNCOES:
        session.run("MERGE (f:Funcao {id: $id}) SET f.descricao = $descricao", {"id": fun["id"], "descricao": fun["descricao"]})
        session.run(
            "MATCH (a:Ativo {id: $atv_id}), (f:Funcao {id: $fun_id}) MERGE (a)-[:DESEMPENHA]->(f)",
            {"atv_id": fun["ativo"], "fun_id": fun["id"]},
        )

    session.run("MERGE (po:ProcessoOperacional {id: $id}) SET po.descricao = $descricao", PROCESSO)
    for fun in FUNCOES:
        session.run(
            "MATCH (po:ProcessoOperacional {id: $po_id}), (f:Funcao {id: $fun_id}) MERGE (po)-[:REQUER]->(f)",
            {"po_id": PROCESSO["id"], "fun_id": fun["id"]},
        )
    session.run("MERGE (e:Entrega {id: $id}) SET e.descricao = $descricao", ENTREGA)
    session.run(
        "MATCH (e:Entrega {id: $ent_id}), (po:ProcessoOperacional {id: $po_id}) MERGE (e)-[:VINCULADA]->(po)",
        {"ent_id": ENTREGA["id"], "po_id": PROCESSO["id"]},
    )
    session.run("MERGE (c:Contrato {id: $id}) SET c.descricao = $descricao", CONTRATO)
    session.run(
        "MATCH (c:Contrato {id: $con_id}), (e:Entrega {id: $ent_id}) MERGE (c)-[:TEM_ENTREGA]->(e)",
        {"con_id": CONTRATO["id"], "ent_id": ENTREGA["id"]},
    )


def _criar_topologia(session) -> None:
    for origem, destino in ALIMENTA:
        session.run("MATCH (a1:Ativo {id: $o}), (a2:Ativo {id: $d}) MERGE (a1)-[:ALIMENTA]->(a2)", {"o": origem, "d": destino})
    for a1, a2, cap in REDUNDA_COM:
        session.run("MATCH (a1:Ativo {id: $o}), (a2:Ativo {id: $d}) MERGE (a1)-[r:REDUNDA_COM]->(a2) SET r.capacidade = $cap", {"o": a1, "d": a2, "cap": cap})


def _criar_defeitos(session) -> None:
    for d in DEFEITOS:
        session.run("MERGE (df:Defeito {id: $id}) SET df.descricao = $descricao, df.status = $status", {"id": d["id"], "descricao": d["descricao"], "status": d["status"]})
        session.run("MATCH (df:Defeito {id: $df_id}), (eq:Equipamento {id: $eq_id}) MERGE (df)-[:DETECTADO_EM]->(eq)", {"df_id": d["id"], "eq_id": d["equipamento"]})
        session.run("MATCH (df:Defeito {id: $df_id}), (mf:ModoFalha {id: $mf_id}) MERGE (df)-[:MANIFESTOU]->(mf)", {"df_id": d["id"], "mf_id": d["modo"]})
        session.run("MATCH (df:Defeito {id: $df_id}), (cf:CausaFalha {id: $cf_id}) MERGE (df)-[:CAUSADO_POR]->(cf)", {"df_id": d["id"], "cf_id": d["causa"]})
        session.run("MATCH (df:Defeito {id: $df_id}), (mec:MecanismoFalha {id: $mec_id}) MERGE (df)-[:VIA_MECANISMO]->(mec)", {"df_id": d["id"], "mec_id": d["mecanismo"]})
    print(f"  {len(DEFEITOS)} defeitos criados.")


def _criar_catalogo_acoes_permitidas(session, modos: list[dict]) -> None:
    acoes = carregar_acoes_permitidas()
    modos_ids = {m["codigo"] for m in modos}

    for papel in PAPEIS:
        session.run(
            "MERGE (p:Papel {id: $id}) SET p.descricao = $descricao, p.nivel = $nivel",
            papel,
        )

    for acao in acoes:
        viabilidade = VIABILIDADE_POR_COMPLEXIDADE.get(acao["complexidade"], 0.5)
        session.run(
            "MERGE (ap:AcaoPermitida {id: $id}) "
            "SET ap.descricao = $descricao, ap.tipo = $tipo, "
            "    ap.complexidade = $complexidade",
            {
                "id": acao["codigo"],
                "descricao": acao["descricao"],
                "tipo": acao["tipo"],
                "complexidade": acao["complexidade"],
            },
        )

        for modo_id in acao.get("modos_aplicaveis", []):
            if modo_id in modos_ids:
                session.run(
                    "MATCH (ap:AcaoPermitida {id: $ap_id}), (mf:ModoFalha {id: $mf_id}) "
                    "MERGE (ap)-[:APLICAVEL_MODO]->(mf)",
                    {"ap_id": acao["codigo"], "mf_id": modo_id},
                )

        classes_com_modo = set()
        for modo in modos:
            if modo["codigo"] in acao.get("modos_aplicaveis", []):
                for ct_id in modo.get("aplicavel_a", []):
                    classes_com_modo.add(ct_id)

        for ct_id in classes_com_modo:
            session.run(
                "MATCH (ct:ClasseTaxonomia {id: $ct_id}), (ap:AcaoPermitida {id: $ap_id}) "
                "MERGE (ct)-[r:PERMITE]->(ap) SET r.viabilidade = $viab",
                {"ct_id": ct_id, "ap_id": acao["codigo"], "viab": viabilidade},
            )

        papeis_autorizados = AUTORIZACAO_POR_COMPLEXIDADE.get(
            acao["complexidade"], ["PAPEL-ENG"],
        )
        for papel_id in papeis_autorizados:
            session.run(
                "MATCH (p:Papel {id: $p_id}), (ap:AcaoPermitida {id: $ap_id}) "
                "MERGE (p)-[:AUTORIZA]->(ap)",
                {"p_id": papel_id, "ap_id": acao["codigo"]},
            )

    print(f"  {len(acoes)} acoes permitidas criadas com {len(PAPEIS)} papeis autorizadores.")


def seed() -> None:
    """Executa o seeder eletrico completo."""
    print("=== Seeder Eletrico ===")

    print("1. Executando migrations...")
    migration_001 = importlib.import_module("ontology.migrations.001_initial_schema")
    migration_001.migrate()
    migration_002 = importlib.import_module("ontology.migrations.002_acao_permitida")
    migration_002.migrate()

    driver = create_driver()
    rng = np.random.default_rng(SEED)

    try:
        with driver.session() as session:
            print("2. Criando normas e organizacao...")
            _criar_normas_e_organizacao(session)

            print("3. Criando taxonomia ISO 14224...")
            classes = carregar_classes_taxonomia()
            _criar_taxonomia(session, classes)

            modos = carregar_modos_falha()
            causas = carregar_causas_falha()
            mecanismos = carregar_mecanismos_falha()
            _criar_modos_causas_mecanismos(session, modos, causas, mecanismos)

            print("4. Criando hierarquia fisica...")
            _criar_hierarquia(session)

            print("5. Criando equipamentos...")
            fab_ids = [f["id"] for f in FABRICANTES]
            _criar_equipamentos(session, fab_ids, rng)

            print("6. Gerando eventos de falha (Poisson + PERFIL_UNIFORME)...")
            lambdas = carregar_lambda_verdadeiro()
            historicos = _gerar_e_criar_eventos(session, lambdas, modos, causas, mecanismos, rng)

            print("7. Criando metricas de confiabilidade...")
            _criar_metricas(session, historicos)

            print("8. Criando funcoes, processos, entregas, contratos...")
            _criar_funcoes_e_processos(session)

            print("9. Criando topologia...")
            _criar_topologia(session)

            print("10. Criando defeitos abertos...")
            _criar_defeitos(session)

            print("11. Criando catalogo de acoes permitidas e papeis...")
            _criar_catalogo_acoes_permitidas(session, modos)

            print("12. Criando requisitos normativos...")
            n_req = comum.criar_normas_e_requisitos(session, carregar_normas())
            print(f"  {n_req} requisitos criados.")

            print("12. Criando planos de manutencao e listas de tarefa...")
            n_pm = comum.criar_planos_manutencao(session)
            print(f"  {n_pm} planos criados.")

            print("12. Criando indicadores de processo...")
            n_ind = comum.criar_indicadores(session)
            print(f"  {n_ind} indicadores criados.")

            # Precisa vir ANTES das funcoes derivadas (partes, etapas): elas
            # olham defeitos e ordens existentes, e rodar depois faria a
            # primeira passada divergir da segunda.
            print("12. Criando defeitos resolvidos com cadeia completa...")
            n_res = comum.criar_defeitos_resolvidos(session, DEFEITOS_RESOLVIDOS)
            print(f"  {n_res} defeitos resolvidos criados.")

            print("12. Criando partes de objeto e localizando defeitos...")
            n_po = comum.criar_partes_objeto(session)
            print(f"  {n_po} localizacoes de defeito criadas.")

            print("12. Criando consequencias de nota...")
            n_cns = comum.criar_consequencias_nota(session)
            print(f"  {n_cns} notas atreladas a consequencia.")

            print("12. Criando etapas das ordens corretivas...")
            n_etp = comum.criar_etapas_das_ordens(session)
            print(f"  {n_etp} etapas criadas.")

            print("12. Ligando organizacao (centro de trabalho, planejamento)...")
            comum.ligar_organizacao(session)

        print("=== Seeder Eletrico concluido com sucesso ===")
    finally:
        driver.close()


if __name__ == "__main__":
    seed()
