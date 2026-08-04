"""Seeder do setor agro — armazenagem de graos.

Popula o grafo com dados sinteticos de uma planta de processamento
e armazenagem, usando perfil sazonal de operacao e lambda de referencia ISO 14224.

Idempotente: usa MERGE em todos os nos. Rodar duas vezes produz o mesmo grafo.
Deterministico: semente fixa para reprodutibilidade.
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
from seed.generator.poisson import PERFIL_SAFRA_AGRO, gerar_historico

SEED = 2
N_MESES = 24

# ---------------------------------------------------------------------------
# Definição da planta — hierarquia física
# ---------------------------------------------------------------------------

EDIFICACAO = {
    "id": "EDIF-001",
    "descricao": "Unidade de processamento 01",
}

SISTEMAS = [
    {"id": "SIS-REC", "descricao": "Recebimento"},
    {"id": "SIS-PRT", "descricao": "Processamento termico"},
    {"id": "SIS-ARM", "descricao": "Armazenagem"},
    {"id": "SIS-EXP", "descricao": "Expedicao"},
    {"id": "SIS-UTI", "descricao": "Utilidades"},
]

ATIVOS = [
    {"id": "ATV-REC-01", "descricao": "Linha de recebimento 01", "sistema": "SIS-REC"},
    {"id": "ATV-PRT-01", "descricao": "Unidade de secagem 01", "sistema": "SIS-PRT"},
    {"id": "ATV-PRT-02", "descricao": "Unidade de secagem 02", "sistema": "SIS-PRT"},
    {"id": "ATV-ARM-01", "descricao": "Modulo de armazenagem 01", "sistema": "SIS-ARM"},
    {"id": "ATV-ARM-02", "descricao": "Modulo de armazenagem 02", "sistema": "SIS-ARM"},
    {"id": "ATV-EXP-01", "descricao": "Linha de expedicao 01", "sistema": "SIS-EXP"},
    {"id": "ATV-UTI-01", "descricao": "Subestacao eletrica", "sistema": "SIS-UTI"},
    {"id": "ATV-UTI-02", "descricao": "Central de utilidades", "sistema": "SIS-UTI"},
]

EQUIPAMENTOS = [
    # Recebimento
    {"id": "EQ-TRE-001", "descricao": "Transportador correia REC-01", "classe": "CT-TRE", "ativo": "ATV-REC-01"},
    {"id": "EQ-ELB-001", "descricao": "Elevador canecas REC-01", "classe": "CT-ELB", "ativo": "ATV-REC-01"},
    {"id": "EQ-MOE-001", "descricao": "Motor eletrico REC-01A", "classe": "CT-MOE", "ativo": "ATV-REC-01"},
    {"id": "EQ-MOE-002", "descricao": "Motor eletrico REC-01B", "classe": "CT-MOE", "ativo": "ATV-REC-01"},
    # Processamento térmico 01
    {"id": "EQ-SEC-001", "descricao": "Secador PRT-01", "classe": "CT-SEC", "ativo": "ATV-PRT-01"},
    {"id": "EQ-VEN-001", "descricao": "Ventilador PRT-01", "classe": "CT-VEN", "ativo": "ATV-PRT-01"},
    {"id": "EQ-MOE-003", "descricao": "Motor eletrico PRT-01", "classe": "CT-MOE", "ativo": "ATV-PRT-01"},
    # Processamento térmico 02
    {"id": "EQ-SEC-002", "descricao": "Secador PRT-02", "classe": "CT-SEC", "ativo": "ATV-PRT-02"},
    {"id": "EQ-VEN-002", "descricao": "Ventilador PRT-02", "classe": "CT-VEN", "ativo": "ATV-PRT-02"},
    {"id": "EQ-MOE-004", "descricao": "Motor eletrico PRT-02", "classe": "CT-MOE", "ativo": "ATV-PRT-02"},
    # Armazenagem 01
    {"id": "EQ-TRE-002", "descricao": "Transportador correia ARM-01", "classe": "CT-TRE", "ativo": "ATV-ARM-01"},
    {"id": "EQ-VCT-001", "descricao": "Valvula controle ARM-01", "classe": "CT-VCT", "ativo": "ATV-ARM-01"},
    {"id": "EQ-VMA-001", "descricao": "Valvula manual ARM-01A", "classe": "CT-VMA", "ativo": "ATV-ARM-01"},
    {"id": "EQ-VMA-002", "descricao": "Valvula manual ARM-01B", "classe": "CT-VMA", "ativo": "ATV-ARM-01"},
    # Armazenagem 02
    {"id": "EQ-VCT-002", "descricao": "Valvula controle ARM-02", "classe": "CT-VCT", "ativo": "ATV-ARM-02"},
    {"id": "EQ-VMA-003", "descricao": "Valvula manual ARM-02", "classe": "CT-VMA", "ativo": "ATV-ARM-02"},
    {"id": "EQ-VSG-001", "descricao": "Valvula seguranca ARM-02", "classe": "CT-VSG", "ativo": "ATV-ARM-02"},
    # Expedição
    {"id": "EQ-TRE-003", "descricao": "Transportador correia EXP-01", "classe": "CT-TRE", "ativo": "ATV-EXP-01"},
    {"id": "EQ-ELB-002", "descricao": "Elevador canecas EXP-01", "classe": "CT-ELB", "ativo": "ATV-EXP-01"},
    {"id": "EQ-BCC-001", "descricao": "Bomba centrifuga EXP-01", "classe": "CT-BCC", "ativo": "ATV-EXP-01"},
    {"id": "EQ-BCP-001", "descricao": "Bomba pistao EXP-01", "classe": "CT-BCP", "ativo": "ATV-EXP-01"},
    {"id": "EQ-MOE-005", "descricao": "Motor eletrico EXP-01", "classe": "CT-MOE", "ativo": "ATV-EXP-01"},
    # Utilidades — subestação
    {"id": "EQ-TRF-001", "descricao": "Transformador UTI-01", "classe": "CT-TRF", "ativo": "ATV-UTI-01"},
    {"id": "EQ-DJT-001", "descricao": "Disjuntor UTI-01A", "classe": "CT-DJT", "ativo": "ATV-UTI-01"},
    {"id": "EQ-DJT-002", "descricao": "Disjuntor UTI-01B", "classe": "CT-DJT", "ativo": "ATV-UTI-01"},
    {"id": "EQ-GER-001", "descricao": "Gerador UTI-01", "classe": "CT-GER", "ativo": "ATV-UTI-01"},
    # Utilidades — central
    {"id": "EQ-CMP-001", "descricao": "Compressor UTI-02", "classe": "CT-CMP", "ativo": "ATV-UTI-02"},
    {"id": "EQ-TCL-001", "descricao": "Trocador calor UTI-02", "classe": "CT-TCL", "ativo": "ATV-UTI-02"},
]

NORMAS = [
    {"id": "NORMA-ISO14224", "codigo": "ISO 14224:2016", "descricao": "Coleta e intercambio de dados de confiabilidade"},
    {"id": "NORMA-NR12", "codigo": "NR-12", "descricao": "Seguranca no trabalho em maquinas e equipamentos"},
]

FABRICANTES = [
    {"id": "FAB-001", "nome": "Fabricante Alpha", "pais": "BR"},
    {"id": "FAB-002", "nome": "Fabricante Beta", "pais": "BR"},
    {"id": "FAB-003", "nome": "Fabricante Gamma", "pais": "DE"},
]

CENTRO_TRABALHO = {"id": "CT-MNT-001", "descricao": "Centro de manutencao industrial"}
EQUIPE = {"id": "EQP-001", "descricao": "Equipe de manutencao mecanica"}
GRUPO_PLANEJAMENTO = {"id": "GPJ-001", "descricao": "Planejamento central"}

# ---------------------------------------------------------------------------
# Funções, processos, entregas, contratos
# ---------------------------------------------------------------------------

FUNCOES = [
    {"id": "FUN-REC", "descricao": "Recebimento de material", "ativo": "ATV-REC-01"},
    {"id": "FUN-PRT-01", "descricao": "Processamento termico 01", "ativo": "ATV-PRT-01"},
    {"id": "FUN-PRT-02", "descricao": "Processamento termico 02", "ativo": "ATV-PRT-02"},
    {"id": "FUN-ARM-01", "descricao": "Armazenagem 01", "ativo": "ATV-ARM-01"},
    {"id": "FUN-ARM-02", "descricao": "Armazenagem 02", "ativo": "ATV-ARM-02"},
    {"id": "FUN-EXP", "descricao": "Expedicao", "ativo": "ATV-EXP-01"},
    {"id": "FUN-ENR", "descricao": "Fornecimento de energia", "ativo": "ATV-UTI-01"},
    {"id": "FUN-UTL", "descricao": "Utilidades gerais", "ativo": "ATV-UTI-02"},
]

PROCESSO = {"id": "PO-001", "descricao": "Processamento e armazenagem"}
ENTREGA = {"id": "ENT-001", "descricao": "Disponibilidade operacional"}
CONTRATO = {"id": "CON-001", "descricao": "Contrato de operacao"}

# ---------------------------------------------------------------------------
# Topologia: ALIMENTA e REDUNDA_COM
# ---------------------------------------------------------------------------

ALIMENTA = [
    ("ATV-REC-01", "ATV-PRT-01"),
    ("ATV-REC-01", "ATV-PRT-02"),
    ("ATV-PRT-01", "ATV-ARM-01"),
    ("ATV-PRT-02", "ATV-ARM-02"),
    ("ATV-ARM-01", "ATV-EXP-01"),
    ("ATV-ARM-02", "ATV-EXP-01"),
]

REDUNDA_COM = [
    ("ATV-PRT-01", "ATV-PRT-02", 0.6),
]

# ---------------------------------------------------------------------------
# Defeitos abertos (5) — DEF-001 é o protagonista
# ---------------------------------------------------------------------------

DEFEITOS = [
    {
        "id": "DEF-001",
        "descricao": "Vibracao anormal progressiva",
        "equipamento": "EQ-TRE-001",
        "modo": "VIB",
        "causa": "AGE",
        "mecanismo": "WEA",
        "status": "aberto",
    },
    {
        "id": "DEF-002",
        "descricao": "Vazamento externo em selo",
        "equipamento": "EQ-VCT-001",
        "modo": "ELP",
        "causa": "AGE",
        "mecanismo": "LEA",
        "status": "aberto",
    },
    {
        "id": "DEF-003",
        "descricao": "Temperatura acima do normal",
        "equipamento": "EQ-MOE-003",
        "modo": "OHE",
        "causa": "OPE",
        "mecanismo": "OVH",
        "status": "aberto",
    },
    {
        "id": "DEF-004",
        "descricao": "Desalinhamento de eixo",
        "equipamento": "EQ-ELB-001",
        "modo": "VIB",
        "causa": "MNT",
        "mecanismo": "MAL",
        "status": "aberto",
    },
    {
        "id": "DEF-005",
        "descricao": "Desgaste em impelidor",
        "equipamento": "EQ-BCC-001",
        "modo": "ERO",
        "causa": "AGE",
        "mecanismo": "ERO",
        "status": "aberto",
    },
]

PROTAGONISTA_ID = "DEF-001"

# Defeitos ja encerrados, com cadeia de falha completa. Existem para que
# `cadeia_falha` tenha o que mostrar: os defeitos abertos acima nao tem
# evento, nota nem acao tomada, o que esta certo mas nao demonstra nada.
DEFEITOS_RESOLVIDOS = [
    {
        "id": "DEF-901",
        "descricao": "Vibracao em mancal de acionamento",
        "equipamento": "EQ-TRE-002",
        "modo": "VIB", "causa": "AGE", "mecanismo": "WEA",
        "horas_deteccao": 8200, "horas_encerramento": 8460, "ano": 2,
        "acao_tomada": "Substituicao de rolamento e realinhamento",
        "horas_execucao": 6.5,
    },
    {
        "id": "DEF-902",
        "descricao": "Vazamento externo em valvula de controle",
        "equipamento": "EQ-VCT-002",
        "modo": "ELP", "causa": "AGE", "mecanismo": "LEA",
        "horas_deteccao": 7100, "horas_encerramento": 7180, "ano": 2,
        "acao_tomada": "Troca de vedacao e teste de estanqueidade",
        "horas_execucao": 3.0,
    },
]

# ---------------------------------------------------------------------------
# Monitoramento de condição — protagonista com tendência crescente
# ---------------------------------------------------------------------------

SENSOR_PROTAGONISTA = {"id": "SEN-VIB-001", "tipo": "acelerometro", "equipamento": "EQ-TRE-001"}
PONTO_MEDICAO_PROTAGONISTA = {"id": "PM-VIB-001", "grandeza": "vibracao_mm_s", "limite_alarme": 7.1}

N_REGISTROS_CONDICAO = 20

# ---------------------------------------------------------------------------
# Papéis autorizadores (F8)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _equipamentos_por_classe() -> dict[str, list[dict]]:
    """Agrupa equipamentos por classe taxonômica."""
    por_classe: dict[str, list[dict]] = defaultdict(list)
    for eq in EQUIPAMENTOS:
        por_classe[eq["classe"]].append(eq)
    return dict(por_classe)


def _modos_para_classe(modos: list[dict], classe_id: str) -> list[dict]:
    """Filtra modos de falha aplicáveis a uma classe."""
    return [m for m in modos if classe_id in m.get("aplicavel_a", [])]


# ---------------------------------------------------------------------------
# Criação de nós e arestas no grafo
# ---------------------------------------------------------------------------

def _criar_hierarquia(session) -> None:
    """Cria Edificacao, Sistemas, Ativos e relacionamentos CONTEM."""
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
    """Cria ClasseTaxonomia nodes a partir das fixtures."""
    for c in classes:
        session.run(
            "MERGE (ct:ClasseTaxonomia {id: $id}) "
            "SET ct.descricao = $descricao, ct.lambda_ref_1e6h = $lambda_ref",
            {
                "id": c["classe_id"],
                "descricao": c["descricao"],
                "lambda_ref": c["lambda_ref_1e6h"],
            },
        )


def _criar_modos_causas_mecanismos(
    session,
    modos: list[dict],
    causas: list[dict],
    mecanismos: list[dict],
) -> None:
    """Cria nós de ModoFalha, CausaFalha, MecanismoFalha."""
    for m in modos:
        session.run(
            "MERGE (mf:ModoFalha {id: $id}) SET mf.descricao = $descricao",
            {"id": m["codigo"], "descricao": m["descricao"]},
        )

    for c in causas:
        session.run(
            "MERGE (cf:CausaFalha {id: $id}) SET cf.descricao = $descricao",
            {"id": c["codigo"], "descricao": c["descricao"]},
        )

    for mec in mecanismos:
        session.run(
            "MERGE (mec:MecanismoFalha {id: $id}) SET mec.descricao = $descricao",
            {"id": mec["codigo"], "descricao": mec["descricao"]},
        )


def _criar_equipamentos(session, fabricantes_ids: list[str], rng) -> None:
    """Cria Equipamento nodes e liga a Ativo e ClasseTaxonomia."""
    for eq in EQUIPAMENTOS:
        fab_id = rng.choice(fabricantes_ids)
        session.run(
            "MERGE (eq:Equipamento {id: $id}) "
            "SET eq.descricao = $descricao, eq.tag = $id",
            {"id": eq["id"], "descricao": eq["descricao"]},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (a:Ativo {id: $atv_id}) "
            "MERGE (eq)-[:PERTENCE]->(a)",
            {"eq_id": eq["id"], "atv_id": eq["ativo"]},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (ct:ClasseTaxonomia {id: $ct_id}) "
            "MERGE (eq)-[:CLASSIFICADO_COMO]->(ct)",
            {"eq_id": eq["id"], "ct_id": eq["classe"]},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (f:Fabricante {id: $fab_id}) "
            "MERGE (eq)-[:FABRICADO]->(f)",
            {"eq_id": eq["id"], "fab_id": fab_id},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (ct:CentroTrabalho {id: $ct_id}) "
            "MERGE (eq)-[:MANTIDO_POR]->(ct)",
            {"eq_id": eq["id"], "ct_id": CENTRO_TRABALHO["id"]},
        )


def _criar_normas_e_organizacao(session) -> None:
    """Cria Norma, Fabricante, CentroTrabalho, Equipe, GrupoPlanejamento."""
    for n in NORMAS:
        session.run(
            "MERGE (n:Norma {id: $id}) SET n.codigo = $codigo, n.descricao = $descricao",
            n,
        )

    for f in FABRICANTES:
        session.run(
            "MERGE (f:Fabricante {id: $id}) SET f.nome = $nome, f.pais = $pais",
            f,
        )

    session.run(
        "MERGE (ct:CentroTrabalho {id: $id}) SET ct.descricao = $descricao",
        CENTRO_TRABALHO,
    )
    session.run(
        "MERGE (eq:Equipe {id: $id}) SET eq.descricao = $descricao",
        EQUIPE,
    )
    session.run(
        "MERGE (gp:GrupoPlanejamento {id: $id}) SET gp.descricao = $descricao",
        GRUPO_PLANEJAMENTO,
    )

    # A ligacao ClasseTaxonomia-REGULADO_POR->Norma nao pode ficar aqui: esta
    # funcao roda antes da taxonomia existir. Ver comum.ligar_organizacao().


def _gerar_e_criar_eventos(
    session,
    lambdas: dict[str, float],
    modos: list[dict],
    causas: list[dict],
    mecanismos: list[dict],
    rng,
) -> dict[str, list]:
    """Gera eventos de falha via Poisson e cria nós no grafo.

    Retorna dict {classe_id: [HistoricoGerado]} para cálculo de métricas.
    """
    eq_por_classe = _equipamentos_por_classe()
    historicos_por_classe: dict[str, list] = defaultdict(list)
    evento_counter = 0
    nota_counter = 0
    ordem_counter = 0

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
                perfil=PERFIL_SAFRA_AGRO,
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
                    "SET ef.timestamp_horas_operacao = $ts_hop, "
                    "    ef.ano = $ano, ef.mes = $mes, "
                    "    ef.hora_calendario = $hora_cal",
                    {
                        "id": ev_id,
                        "ts_hop": evento.timestamp_horas_operacao,
                        "ano": evento.ano,
                        "mes": evento.mes,
                        "hora_cal": evento.hora_calendario,
                    },
                )

                session.run(
                    "MATCH (ef:EventoFalha {id: $ef_id}), (eq:Equipamento {id: $eq_id}) "
                    "MERGE (ef)-[:OCORREU]->(eq)",
                    {"ef_id": ev_id, "eq_id": eq["id"]},
                )
                session.run(
                    "MATCH (ef:EventoFalha {id: $ef_id}), (mf:ModoFalha {id: $mf_id}) "
                    "MERGE (ef)-[:MANIFESTOU]->(mf)",
                    {"ef_id": ev_id, "mf_id": modo_id},
                )
                session.run(
                    "MATCH (ef:EventoFalha {id: $ef_id}), (cf:CausaFalha {id: $cf_id}) "
                    "MERGE (ef)-[:CAUSADO_POR]->(cf)",
                    {"ef_id": ev_id, "cf_id": causa_id},
                )
                session.run(
                    "MATCH (ef:EventoFalha {id: $ef_id}), (mec:MecanismoFalha {id: $mec_id}) "
                    "MERGE (ef)-[:VIA_MECANISMO]->(mec)",
                    {"ef_id": ev_id, "mec_id": mec_id},
                )

                # Maintenance workflow: EventoFalha -> NotaManutencao -> OrdemManutencao
                session.run(
                    "MERGE (nm:NotaManutencao {id: $id}) "
                    "SET nm.descricao = $descricao, nm.tipo = 'corretiva'",
                    {"id": nota_id, "descricao": f"Nota referente a {ev_id}"},
                )
                session.run(
                    "MATCH (ef:EventoFalha {id: $ef_id}), (nm:NotaManutencao {id: $nm_id}) "
                    "MERGE (ef)-[:GEROU]->(nm)",
                    {"ef_id": ev_id, "nm_id": nota_id},
                )
                session.run(
                    "MATCH (nm:NotaManutencao {id: $nm_id}), (eq:Equipamento {id: $eq_id}) "
                    "MERGE (nm)-[:ATRIBUIDA]->(eq)",
                    {"nm_id": nota_id, "eq_id": eq["id"]},
                )
                session.run(
                    "MATCH (nm:NotaManutencao {id: $nm_id}), (ct:CentroTrabalho {id: $ct_id}) "
                    "MERGE (nm)-[:EXECUTADA_CT]->(ct)",
                    {"nm_id": nota_id, "ct_id": CENTRO_TRABALHO["id"]},
                )

                session.run(
                    "MERGE (om:OrdemManutencao {id: $id}) "
                    "SET om.descricao = $descricao, om.tipo = 'corretiva'",
                    {"id": ordem_id, "descricao": f"Ordem referente a {nota_id}"},
                )
                session.run(
                    "MATCH (nm:NotaManutencao {id: $nm_id}), (om:OrdemManutencao {id: $om_id}) "
                    "MERGE (nm)-[:GEROU_ORDEM]->(om)",
                    {"nm_id": nota_id, "om_id": ordem_id},
                )
                session.run(
                    "MATCH (om:OrdemManutencao {id: $om_id}), (eq:Equipamento {id: $eq_id}) "
                    "MERGE (om)-[:EXECUTADA_EM]->(eq)",
                    {"om_id": ordem_id, "eq_id": eq["id"]},
                )
                session.run(
                    "MATCH (om:OrdemManutencao {id: $om_id}), (ef:EventoFalha {id: $ef_id}) "
                    "MERGE (om)-[:RESOLVE]->(ef)",
                    {"om_id": ordem_id, "ef_id": ev_id},
                )

    print(f"  {evento_counter} eventos de falha criados.")
    print(f"  {nota_counter} notas de manutencao criadas.")
    print(f"  {ordem_counter} ordens de manutencao criadas.")
    return dict(historicos_por_classe)


def _criar_metricas(session, historicos_por_classe: dict[str, list]) -> None:
    """Cria MetricaConfiabilidade por classe taxonômica (agregada)."""
    for classe_id, historicos in historicos_por_classe.items():
        n_total = sum(len(h.eventos) for h in historicos)
        hop_total = sum(h.horas_operacao_total for h in historicos)

        if hop_total <= 0:
            continue

        from seed.generator.poisson import HistoricoGerado, EventoFalhaGerado

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

        metrica_id = f"MC-{classe_id}"
        session.run(
            "MERGE (mc:MetricaConfiabilidade {id: $id}) "
            "SET mc.lambda_hat = $lambda_hat, "
            "    mc.ic_inferior = $ic_inf, "
            "    mc.ic_superior = $ic_sup, "
            "    mc.n_eventos = $n_ev, "
            "    mc.horas_operacao = $hop, "
            "    mc.nivel_confianca = $nc, "
            "    mc.metodo = 'MLE_chi2'",
            {
                "id": metrica_id,
                "lambda_hat": est.lambda_hat,
                "ic_inf": est.ic_inferior,
                "ic_sup": est.ic_superior,
                "n_ev": est.n_eventos,
                "hop": est.horas_operacao,
                "nc": est.nivel_confianca,
            },
        )
        session.run(
            "MATCH (ct:ClasseTaxonomia {id: $ct_id}), (mc:MetricaConfiabilidade {id: $mc_id}) "
            "MERGE (ct)-[:TEM_METRICA]->(mc)",
            {"ct_id": classe_id, "mc_id": metrica_id},
        )

    print(f"  {len(historicos_por_classe)} metricas de confiabilidade criadas.")


def _criar_funcoes_e_processos(session) -> None:
    """Cria Funcao, ProcessoOperacional, Entrega, Contrato e suas arestas."""
    for fun in FUNCOES:
        session.run(
            "MERGE (f:Funcao {id: $id}) SET f.descricao = $descricao",
            {"id": fun["id"], "descricao": fun["descricao"]},
        )
        session.run(
            "MATCH (a:Ativo {id: $atv_id}), (f:Funcao {id: $fun_id}) "
            "MERGE (a)-[:DESEMPENHA]->(f)",
            {"atv_id": fun["ativo"], "fun_id": fun["id"]},
        )

    session.run(
        "MERGE (po:ProcessoOperacional {id: $id}) SET po.descricao = $descricao",
        PROCESSO,
    )
    for fun in FUNCOES:
        session.run(
            "MATCH (po:ProcessoOperacional {id: $po_id}), (f:Funcao {id: $fun_id}) "
            "MERGE (po)-[:REQUER]->(f)",
            {"po_id": PROCESSO["id"], "fun_id": fun["id"]},
        )

    session.run(
        "MERGE (e:Entrega {id: $id}) SET e.descricao = $descricao",
        ENTREGA,
    )
    session.run(
        "MATCH (e:Entrega {id: $ent_id}), (po:ProcessoOperacional {id: $po_id}) "
        "MERGE (e)-[:VINCULADA]->(po)",
        {"ent_id": ENTREGA["id"], "po_id": PROCESSO["id"]},
    )

    session.run(
        "MERGE (c:Contrato {id: $id}) SET c.descricao = $descricao",
        CONTRATO,
    )
    session.run(
        "MATCH (c:Contrato {id: $con_id}), (e:Entrega {id: $ent_id}) "
        "MERGE (c)-[:TEM_ENTREGA]->(e)",
        {"con_id": CONTRATO["id"], "ent_id": ENTREGA["id"]},
    )


def _criar_topologia(session) -> None:
    """Cria ALIMENTA e REDUNDA_COM entre ativos."""
    for origem, destino in ALIMENTA:
        session.run(
            "MATCH (a1:Ativo {id: $o}), (a2:Ativo {id: $d}) "
            "MERGE (a1)-[:ALIMENTA]->(a2)",
            {"o": origem, "d": destino},
        )

    for a1, a2, cap in REDUNDA_COM:
        session.run(
            "MATCH (a1:Ativo {id: $o}), (a2:Ativo {id: $d}) "
            "MERGE (a1)-[r:REDUNDA_COM]->(a2) SET r.capacidade = $cap",
            {"o": a1, "d": a2, "cap": cap},
        )


def _criar_defeitos(session) -> None:
    """Cria 5 defeitos abertos com o protagonista."""
    for d in DEFEITOS:
        session.run(
            "MERGE (df:Defeito {id: $id}) "
            "SET df.descricao = $descricao, df.status = $status",
            {"id": d["id"], "descricao": d["descricao"], "status": d["status"]},
        )
        session.run(
            "MATCH (df:Defeito {id: $df_id}), (eq:Equipamento {id: $eq_id}) "
            "MERGE (df)-[:DETECTADO_EM]->(eq)",
            {"df_id": d["id"], "eq_id": d["equipamento"]},
        )
        session.run(
            "MATCH (df:Defeito {id: $df_id}), (mf:ModoFalha {id: $mf_id}) "
            "MERGE (df)-[:MANIFESTOU]->(mf)",
            {"df_id": d["id"], "mf_id": d["modo"]},
        )
        session.run(
            "MATCH (df:Defeito {id: $df_id}), (cf:CausaFalha {id: $cf_id}) "
            "MERGE (df)-[:CAUSADO_POR]->(cf)",
            {"df_id": d["id"], "cf_id": d["causa"]},
        )
        session.run(
            "MATCH (df:Defeito {id: $df_id}), (mec:MecanismoFalha {id: $mec_id}) "
            "MERGE (df)-[:VIA_MECANISMO]->(mec)",
            {"df_id": d["id"], "mec_id": d["mecanismo"]},
        )

    print(f"  {len(DEFEITOS)} defeitos criados (protagonista: {PROTAGONISTA_ID}).")


def _criar_monitoramento_protagonista(session, rng) -> None:
    """Cria sensor, ponto de medição e registros de condição com tendência crescente."""
    eq_id = SENSOR_PROTAGONISTA["equipamento"]

    session.run(
        "MERGE (s:Sensor {id: $id}) SET s.tipo = $tipo",
        SENSOR_PROTAGONISTA,
    )
    session.run(
        "MATCH (eq:Equipamento {id: $eq_id}), (s:Sensor {id: $s_id}) "
        "MERGE (eq)-[:TEM_SENSOR]->(s)",
        {"eq_id": eq_id, "s_id": SENSOR_PROTAGONISTA["id"]},
    )

    pm = PONTO_MEDICAO_PROTAGONISTA
    session.run(
        "MERGE (pm:PontoMedicao {id: $id}) "
        "SET pm.grandeza = $grandeza, pm.limite_alarme = $limite",
        {"id": pm["id"], "grandeza": pm["grandeza"], "limite": pm["limite_alarme"]},
    )
    session.run(
        "MATCH (eq:Equipamento {id: $eq_id}), (pm:PontoMedicao {id: $pm_id}) "
        "MERGE (eq)-[:TEM_PONTO]->(pm)",
        {"eq_id": eq_id, "pm_id": pm["id"]},
    )

    limite = pm["limite_alarme"]
    base = 2.5
    incremento = (limite - base - 0.5) / N_REGISTROS_CONDICAO

    for i in range(N_REGISTROS_CONDICAO):
        rc_id = f"RC-VIB-{i+1:03d}"
        valor = base + incremento * i + float(rng.uniform(-0.15, 0.15))
        session.run(
            "MERGE (rc:RegistroCondicao {id: $id}) "
            "SET rc.valor = $valor, rc.sequencia = $seq",
            {"id": rc_id, "valor": valor, "seq": i + 1},
        )
        session.run(
            "MATCH (eq:Equipamento {id: $eq_id}), (rc:RegistroCondicao {id: $rc_id}) "
            "MERGE (eq)-[:TEM_REGISTRO]->(rc)",
            {"eq_id": eq_id, "rc_id": rc_id},
        )
        session.run(
            "MATCH (rc:RegistroCondicao {id: $rc_id}), (pm:PontoMedicao {id: $pm_id}) "
            "MERGE (rc)-[:PARA_PONTO]->(pm)",
            {"rc_id": rc_id, "pm_id": pm["id"]},
        )

    # RegistroCondicao mais recente DETECTOU o defeito protagonista
    ultimo_rc = f"RC-VIB-{N_REGISTROS_CONDICAO:03d}"
    session.run(
        "MATCH (rc:RegistroCondicao {id: $rc_id}), (df:Defeito {id: $df_id}) "
        "MERGE (rc)-[:DETECTOU]->(df)",
        {"rc_id": ultimo_rc, "df_id": PROTAGONISTA_ID},
    )

    print(f"  {N_REGISTROS_CONDICAO} registros de condicao criados (tendencia crescente).")


def _criar_catalogo_acoes_permitidas(session, modos: list[dict]) -> None:
    """Cria catálogo AcaoPermitida, Papel e suas relações (F8)."""
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


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def seed() -> None:
    """Executa o seeder completo."""
    print("=== Seeder Agro ===")

    print("1. Executando migrations...")
    migration_001 = importlib.import_module("ontology.migrations.001_initial_schema")
    migration_001.migrate()
    migration_002 = importlib.import_module("ontology.migrations.002_acao_permitida")
    migration_002.migrate()
    migration_003 = importlib.import_module("ontology.migrations.003_processo_declarativo")
    migration_003.migrate()

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

            print("6. Gerando eventos de falha (Poisson + PERFIL_SAFRA_AGRO)...")
            lambdas = carregar_lambda_verdadeiro()
            historicos = _gerar_e_criar_eventos(
                session, lambdas, modos, causas, mecanismos, rng,
            )

            print("7. Criando metricas de confiabilidade...")
            _criar_metricas(session, historicos)

            print("8. Criando funcoes, processos, entregas, contratos...")
            _criar_funcoes_e_processos(session)

            print("9. Criando topologia (ALIMENTA, REDUNDA_COM)...")
            _criar_topologia(session)

            print("10. Criando defeitos abertos...")
            _criar_defeitos(session)

            print("11. Criando monitoramento do protagonista...")
            _criar_monitoramento_protagonista(session, rng)

            print("12. Criando catalogo de acoes permitidas e papeis...")
            _criar_catalogo_acoes_permitidas(session, modos)

            print("13. Criando requisitos normativos...")
            n_req = comum.criar_normas_e_requisitos(session, carregar_normas())
            print(f"  {n_req} requisitos criados.")

            print("14. Criando planos de manutencao e listas de tarefa...")
            n_pm = comum.criar_planos_manutencao(session)
            print(f"  {n_pm} planos criados.")

            print("15. Criando indicadores de processo...")
            n_ind = comum.criar_indicadores(session)
            print(f"  {n_ind} indicadores criados.")

            # Precisa vir ANTES das funcoes derivadas (partes, etapas): elas
            # olham defeitos e ordens existentes, e rodar depois faria a
            # primeira passada divergir da segunda.
            print("16. Criando defeitos resolvidos com cadeia completa...")
            n_res = comum.criar_defeitos_resolvidos(session, DEFEITOS_RESOLVIDOS)
            print(f"  {n_res} defeitos resolvidos criados.")

            print("17. Criando partes de objeto e localizando defeitos...")
            n_po = comum.criar_partes_objeto(session)
            print(f"  {n_po} localizacoes de defeito criadas.")

            print("18. Criando consequencias de nota...")
            n_cns = comum.criar_consequencias_nota(session)
            print(f"  {n_cns} notas atreladas a consequencia.")

            print("19. Criando etapas das ordens corretivas...")
            n_etp = comum.criar_etapas_das_ordens(session)
            print(f"  {n_etp} etapas criadas.")

            print("20. Ligando organizacao (centro de trabalho, planejamento)...")
            comum.ligar_organizacao(session)

            print("21. Declarando o processo operacional (regime, estagios)...")
            n_req = comum.enriquecer_processo(session, comum.PROCESSO_AGRO)
            n_pre = comum.ligar_precedencia_processos(session)
            n_ind = comum.medir_indicadores(session)
            print(f"  {n_req} funcoes com ordem e criticidade, "
                  f"{n_pre} precedencia(s), {n_ind} indicador(es) medido(s).")

        print("=== Seeder Agro concluido com sucesso ===")
    finally:
        driver.close()


if __name__ == "__main__":
    seed()
