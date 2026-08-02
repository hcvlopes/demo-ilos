"""Suíte de fumaça — valida que o scaffolding está correto."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_structure_exists():
    """Diretórios essenciais existem."""
    expected_dirs = [
        "ontology",
        "ontology/migrations",
        "fixtures/iso14224",
        "fixtures/calibracao",
        "seed/generator",
        "seed/agro",
        "seed/eletrico",
        "intents/transversais",
        "intents/capacidade",
        "scoring",
        "api",
        "db",
        "vocab/perfis",
        "web",
        "tests",
        "docs",
    ]
    for d in expected_dirs:
        assert (ROOT / d).is_dir(), f"Diretório ausente: {d}"


def test_claude_md_exists():
    """CLAUDE.md existe na raiz."""
    assert (ROOT / "CLAUDE.md").is_file()


def test_claude_md_contains_rules():
    """CLAUDE.md contém as regras invioláveis."""
    content = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "LLM nunca escreve Cypher" in content
    assert "envelope de evidência completo" in content
    assert "Vocabulário setorial nunca entra no grafo" in content
    assert "ISO 14224" in content
    assert "Seeders são idempotentes" in content


def test_fixtures_placeholders_exist():
    """Fixtures ISO 14224 têm placeholders."""
    fixtures = [
        "fixtures/iso14224/modos_falha.yaml",
        "fixtures/iso14224/causas_falha.yaml",
        "fixtures/iso14224/mecanismos_falha.yaml",
        "fixtures/iso14224/classes_taxonomia.yaml",
        "fixtures/calibracao/lambda_verdadeiro.yaml",
    ]
    for f in fixtures:
        assert (ROOT / f).is_file(), f"Fixture ausente: {f}"


def test_vocab_profiles_exist():
    """Perfis setoriais têm placeholders."""
    assert (ROOT / "vocab/perfis/agro.yaml").is_file()
    assert (ROOT / "vocab/perfis/eletrico.yaml").is_file()


def test_docs_initialized():
    """Documentação inicial existe."""
    assert (ROOT / "docs/DECISOES.md").is_file()
    assert (ROOT / "docs/PROGRESSO.md").is_file()
    assert (ROOT / "docs/ONTOLOGIA.md").is_file()


def test_export_schema_runs():
    """export_schema.py é importável e executável."""
    from ontology.export_schema import export_schema
    export_schema()
    content = (ROOT / "docs/ONTOLOGIA.md").read_text(encoding="utf-8")
    assert "Schema vigente" in content
