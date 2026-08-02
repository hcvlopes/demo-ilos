"""Ontologia do grafo de ativos industriais.

Define labels de nó, tipos de aresta, propriedades e constraints de unicidade.
Base: spec colada pelo usuário.
Deltas: 0.A (processo/entrega/contrato/indicador), 0.B (subtipos CONECTADO),
        0.C (norma/requisito), 0.F (métrica de confiabilidade).
"""

# ---------------------------------------------------------------------------
# Node labels
# ---------------------------------------------------------------------------

NODE_LABELS: list[str] = [
    # Hierarquia física
    "Edificacao",
    "Sistema",
    "Ativo",
    "Equipamento",
    "ParteObjeto",
    "Funcao",
    # Taxonomia e fabricação
    "ClasseTaxonomia",
    "Fabricante",
    # Manutenção — organização
    "CentroTrabalho",
    "Equipe",
    "GrupoPlanejamento",
    # Monitoramento
    "Sensor",
    "PontoMedicao",
    "RegistroCondicao",
    # Falhas / defeitos (ISO 14224)
    "Defeito",
    "EventoFalha",
    "CausaFalha",
    "ModoFalha",
    "MecanismoFalha",
    # Manutenção — workflow
    "NotaManutencao",
    "ConsequenciaNota",
    "OrdemManutencao",
    "Etapa",
    "AcaoTomada",
    "Material",
    # Planejamento
    "PlanoManutencao",
    "ListaTarefa",
    # Delta 0.A — processo / entrega / contrato / indicador
    "ProcessoOperacional",
    "Entrega",
    "Contrato",
    "Indicador",
    # Delta 0.C — norma / requisito
    "Norma",
    "Requisito",
    # Delta 0.F — métrica de confiabilidade
    "MetricaConfiabilidade",
    # Delta 0.G — ação permitida e papel autorizador
    "AcaoPermitida",
    "Papel",
]

# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES: list[str] = [
    # Hierarquia física
    "CONTEM",
    "PERTENCE",
    "DESEMPENHA",
    # Delta 0.B — subtipos de CONECTADO (nunca usar CONECTADO genérico)
    "ALIMENTA",
    "REDUNDA_COM",
    # Taxonomia e fabricação
    "CLASSIFICADO_COMO",
    "FABRICADO",
    "MANTIDO_POR",
    # Monitoramento
    "TEM_SENSOR",
    "TEM_PONTO",
    "TEM_REGISTRO",
    "PARA_PONTO",
    "DETECTOU",
    # Defeitos
    "DETECTADO_EM",
    "IDENTIFICADO_EM",
    "CAUSADO_POR",
    "MANIFESTOU",
    "VIA_MECANISMO",
    "EVOLUIU_PARA",
    "GEROU",
    "RESOLVIDO_POR",
    # Eventos de falha
    "OCORREU",
    # Manutenção — workflow
    "ATRIBUIDA",
    "ATRELADA",
    "EXECUTADA_CT",
    "GEROU_ORDEM",
    "EXECUTADA_EM",
    "RESOLVE",
    "TEM_ETAPA",
    "EXECUTADA_POR",
    "USA_MATERIAL",
    # Planejamento
    "COBRE",
    "USA_LISTA",
    "PLANEJADO_POR",
    # Delta 0.A — processo / entrega / contrato
    "TEM_ENTREGA",
    "VINCULADA",
    "REQUER",
    "MEDE",
    # Delta 0.C — norma / requisito
    "TEM_REQUISITO",
    "REGULADO_POR",
    # Delta 0.F — métrica de confiabilidade
    "TEM_METRICA",
    # Delta 0.G — ação permitida e papel autorizador
    "PERMITE",
    "AUTORIZA",
    "APLICAVEL_MODO",
]

# ---------------------------------------------------------------------------
# Relationship signatures: (source_label, rel_type, target_label)
# ---------------------------------------------------------------------------

RELATIONSHIP_SIGNATURES: list[tuple[str, str, str]] = [
    # Hierarquia física
    ("Edificacao", "CONTEM", "Sistema"),
    ("Sistema", "CONTEM", "Sistema"),
    ("Sistema", "CONTEM", "Ativo"),
    ("Equipamento", "PERTENCE", "Ativo"),
    ("ParteObjeto", "PERTENCE", "Equipamento"),
    ("Ativo", "DESEMPENHA", "Funcao"),
    # Delta 0.B — subtipos de CONECTADO
    ("Ativo", "ALIMENTA", "Ativo"),
    ("Ativo", "REDUNDA_COM", "Ativo"),
    # Taxonomia e fabricação
    ("Equipamento", "CLASSIFICADO_COMO", "ClasseTaxonomia"),
    ("Equipamento", "FABRICADO", "Fabricante"),
    ("Equipamento", "MANTIDO_POR", "CentroTrabalho"),
    # Monitoramento
    ("Equipamento", "TEM_SENSOR", "Sensor"),
    ("Equipamento", "TEM_PONTO", "PontoMedicao"),
    ("Equipamento", "TEM_REGISTRO", "RegistroCondicao"),
    ("RegistroCondicao", "PARA_PONTO", "PontoMedicao"),
    ("RegistroCondicao", "DETECTOU", "Defeito"),
    # Defeitos (ISO 14224)
    ("Defeito", "DETECTADO_EM", "Equipamento"),
    ("Defeito", "IDENTIFICADO_EM", "ParteObjeto"),
    ("Defeito", "CAUSADO_POR", "CausaFalha"),
    ("Defeito", "MANIFESTOU", "ModoFalha"),
    ("Defeito", "VIA_MECANISMO", "MecanismoFalha"),
    ("Defeito", "EVOLUIU_PARA", "EventoFalha"),
    ("Defeito", "GEROU", "NotaManutencao"),
    ("Defeito", "RESOLVIDO_POR", "AcaoTomada"),
    # Eventos de falha
    ("EventoFalha", "OCORREU", "Ativo"),
    ("EventoFalha", "OCORREU", "Equipamento"),
    ("EventoFalha", "CAUSADO_POR", "CausaFalha"),
    ("EventoFalha", "MANIFESTOU", "ModoFalha"),
    ("EventoFalha", "VIA_MECANISMO", "MecanismoFalha"),
    ("EventoFalha", "IDENTIFICADO_EM", "ParteObjeto"),
    ("EventoFalha", "GEROU", "NotaManutencao"),
    ("EventoFalha", "RESOLVIDO_POR", "AcaoTomada"),
    # Manutenção — workflow
    ("NotaManutencao", "ATRIBUIDA", "Ativo"),
    ("NotaManutencao", "ATRIBUIDA", "Equipamento"),
    ("NotaManutencao", "ATRELADA", "ConsequenciaNota"),
    ("NotaManutencao", "EXECUTADA_CT", "CentroTrabalho"),
    ("NotaManutencao", "GEROU_ORDEM", "OrdemManutencao"),
    ("OrdemManutencao", "ATRIBUIDA", "Ativo"),
    ("OrdemManutencao", "EXECUTADA_EM", "Equipamento"),
    ("OrdemManutencao", "RESOLVE", "Defeito"),
    ("OrdemManutencao", "RESOLVE", "EventoFalha"),
    ("OrdemManutencao", "TEM_ETAPA", "Etapa"),
    ("Etapa", "EXECUTADA_POR", "Equipe"),
    ("Etapa", "USA_MATERIAL", "Material"),
    # Planejamento
    ("PlanoManutencao", "COBRE", "Ativo"),
    ("PlanoManutencao", "COBRE", "Sistema"),
    ("PlanoManutencao", "USA_LISTA", "ListaTarefa"),
    ("PlanoManutencao", "GEROU_ORDEM", "OrdemManutencao"),
    ("Ativo", "PLANEJADO_POR", "GrupoPlanejamento"),
    ("Sistema", "PLANEJADO_POR", "GrupoPlanejamento"),
    ("Edificacao", "PLANEJADO_POR", "GrupoPlanejamento"),
    ("Equipamento", "PLANEJADO_POR", "GrupoPlanejamento"),
    ("NotaManutencao", "PLANEJADO_POR", "GrupoPlanejamento"),
    ("OrdemManutencao", "PLANEJADO_POR", "GrupoPlanejamento"),
    # Delta 0.A — processo / entrega / contrato / indicador
    ("Contrato", "TEM_ENTREGA", "Entrega"),
    ("Entrega", "VINCULADA", "ProcessoOperacional"),
    ("ProcessoOperacional", "REQUER", "Funcao"),
    ("Indicador", "MEDE", "ProcessoOperacional"),
    # Delta 0.C — norma / requisito
    ("Norma", "TEM_REQUISITO", "Requisito"),
    ("Equipamento", "REGULADO_POR", "Norma"),
    ("ClasseTaxonomia", "REGULADO_POR", "Norma"),
    # Delta 0.F — métrica de confiabilidade
    ("ClasseTaxonomia", "TEM_METRICA", "MetricaConfiabilidade"),
    # Delta 0.G — ação permitida e papel autorizador
    ("ClasseTaxonomia", "PERMITE", "AcaoPermitida"),
    ("AcaoPermitida", "APLICAVEL_MODO", "ModoFalha"),
    ("Papel", "AUTORIZA", "AcaoPermitida"),
]

# ---------------------------------------------------------------------------
# Uniqueness constraints: label -> property
# ---------------------------------------------------------------------------

UNIQUENESS_CONSTRAINTS: dict[str, str] = {label: "id" for label in NODE_LABELS}

# ---------------------------------------------------------------------------
# Relationship properties (non-trivial)
# ---------------------------------------------------------------------------

RELATIONSHIP_PROPERTIES: dict[str, list[str]] = {
    "REDUNDA_COM": ["capacidade"],
    "PERMITE": ["viabilidade"],
}
