"""Testes da ontologia (F1).

Valida schema, idempotência da migration e ausência de CONECTADO genérico.
Testes que não precisam de banco usam schema.py diretamente.
"""

from ontology.schema import (
    NODE_LABELS,
    RELATIONSHIP_PROPERTIES,
    RELATIONSHIP_SIGNATURES,
    RELATIONSHIP_TYPES,
    UNIQUENESS_CONSTRAINTS,
)


# ---------------------------------------------------------------------------
# Schema completude
# ---------------------------------------------------------------------------


def test_all_labels_have_uniqueness_constraint():
    """Todo label tem constraint de unicidade."""
    for label in NODE_LABELS:
        assert label in UNIQUENESS_CONSTRAINTS, (
            f"Label {label} sem constraint de unicidade"
        )


def test_no_duplicate_labels():
    """Sem labels duplicados."""
    assert len(NODE_LABELS) == len(set(NODE_LABELS))


def test_no_duplicate_relationship_types():
    """Sem tipos de aresta duplicados."""
    assert len(RELATIONSHIP_TYPES) == len(set(RELATIONSHIP_TYPES))


def test_signatures_use_declared_labels():
    """Toda assinatura usa labels declarados."""
    label_set = set(NODE_LABELS)
    for src, rel, tgt in RELATIONSHIP_SIGNATURES:
        assert src in label_set, f"Label de origem não declarado: {src}"
        assert tgt in label_set, f"Label de destino não declarado: {tgt}"


def test_signatures_use_declared_relationship_types():
    """Toda assinatura usa tipos de aresta declarados."""
    rel_set = set(RELATIONSHIP_TYPES)
    for _, rel, _ in RELATIONSHIP_SIGNATURES:
        assert rel in rel_set, f"Tipo de aresta não declarado: {rel}"


# ---------------------------------------------------------------------------
# Delta 0.B — CONECTADO genérico proibido
# ---------------------------------------------------------------------------


def test_conectado_generico_proibido():
    """CONECTADO genérico não existe como tipo de aresta."""
    assert "CONECTADO" not in RELATIONSHIP_TYPES, (
        "CONECTADO genérico não deve existir — use subtipos (ALIMENTA, REDUNDA_COM)"
    )


def test_conectado_nao_aparece_em_assinaturas():
    """Nenhuma assinatura usa CONECTADO genérico."""
    for src, rel, tgt in RELATIONSHIP_SIGNATURES:
        assert rel != "CONECTADO", (
            f"Assinatura ({src})-[CONECTADO]->({tgt}) usa tipo genérico proibido"
        )


def test_subtipos_conectado_existem():
    """Subtipos ALIMENTA e REDUNDA_COM existem."""
    assert "ALIMENTA" in RELATIONSHIP_TYPES
    assert "REDUNDA_COM" in RELATIONSHIP_TYPES


def test_redunda_com_tem_propriedade_capacidade():
    """REDUNDA_COM declara propriedade 'capacidade'."""
    props = RELATIONSHIP_PROPERTIES.get("REDUNDA_COM", [])
    assert "capacidade" in props


# ---------------------------------------------------------------------------
# Deltas presentes
# ---------------------------------------------------------------------------


def test_delta_0a_processo_entrega_contrato_indicador():
    """Delta 0.A: labels de processo, entrega, contrato e indicador."""
    for label in ["ProcessoOperacional", "Entrega", "Contrato", "Indicador"]:
        assert label in NODE_LABELS, f"Delta 0.A: {label} ausente"


def test_delta_0a_caminho_contrato_funcao():
    """Delta 0.A: caminho Contrato → Entrega → Processo → Funcao existe."""
    sig_set = set(RELATIONSHIP_SIGNATURES)
    assert ("Contrato", "TEM_ENTREGA", "Entrega") in sig_set
    assert ("Entrega", "VINCULADA", "ProcessoOperacional") in sig_set
    assert ("ProcessoOperacional", "REQUER", "Funcao") in sig_set


def test_delta_0c_norma_requisito():
    """Delta 0.C: Norma e Requisito presentes com relacionamentos."""
    assert "Norma" in NODE_LABELS
    assert "Requisito" in NODE_LABELS
    sig_set = set(RELATIONSHIP_SIGNATURES)
    assert ("Norma", "TEM_REQUISITO", "Requisito") in sig_set


def test_delta_0f_metrica_confiabilidade():
    """Delta 0.F: MetricaConfiabilidade presente e ligada a ClasseTaxonomia."""
    assert "MetricaConfiabilidade" in NODE_LABELS
    sig_set = set(RELATIONSHIP_SIGNATURES)
    assert ("ClasseTaxonomia", "TEM_METRICA", "MetricaConfiabilidade") in sig_set


# ---------------------------------------------------------------------------
# export_schema funciona offline
# ---------------------------------------------------------------------------


def test_export_schema_offline():
    """export_schema gera ONTOLOGIA.md com todos os labels."""
    from pathlib import Path

    from ontology.export_schema import export_schema

    export_schema()
    content = (
        Path(__file__).resolve().parent.parent / "docs" / "ONTOLOGIA.md"
    ).read_text(encoding="utf-8")
    assert "Schema vigente" in content
    for label in NODE_LABELS:
        assert f"`{label}`" in content, f"Label {label} ausente no ONTOLOGIA.md"
    for rel in RELATIONSHIP_TYPES:
        assert f"`{rel}`" in content, f"Aresta {rel} ausente no ONTOLOGIA.md"
