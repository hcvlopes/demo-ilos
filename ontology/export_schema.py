"""Gera docs/ONTOLOGIA.md a partir do schema definido em codigo.

Quando ha banco disponivel, inspeciona indices no FalkorDB.
Quando nao ha, gera a partir de ontology/schema.py (modo offline).
"""

from pathlib import Path

from ontology.schema import (
    NODE_LABELS,
    RELATIONSHIP_PROPERTIES,
    RELATIONSHIP_SIGNATURES,
    RELATIONSHIP_TYPES,
    UNIQUENESS_CONSTRAINTS,
)

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "ONTOLOGIA.md"


def _try_live_indices() -> list[str] | None:
    try:
        from db.adapter import create_driver

        driver = create_driver()
        with driver.session() as session:
            result = session.run("CALL db.indexes()")
            lines = []
            for r in result:
                label = r.get("label", "?")
                props = r.get("properties", [])
                props_str = ", ".join(str(p) for p in props) if isinstance(props, list) else str(props)
                lines.append(f"| {label} | {props_str} |")
            driver.close()
            return lines if lines else None
    except Exception:
        return None


def export_schema() -> None:
    lines = [
        "# Ontologia — Schema vigente",
        "",
        "> Gerado automaticamente por `ontology/export_schema.py`.",
        "> Nao edite manualmente — execute `make schema-doc`.",
        "",
        "---",
        "",
        "## Labels de no",
        "",
        f"Total: **{len(NODE_LABELS)}**",
        "",
        "| # | Label | Indice (propriedade) |",
        "|---|---|---|",
    ]
    for i, label in enumerate(NODE_LABELS, 1):
        prop = UNIQUENESS_CONSTRAINTS.get(label, "—")
        lines.append(f"| {i} | `{label}` | `{prop}` |")

    lines += [
        "",
        "---",
        "",
        "## Tipos de aresta",
        "",
        f"Total: **{len(RELATIONSHIP_TYPES)}**",
        "",
        "| Tipo | Propriedades |",
        "|---|---|",
    ]
    for rt in RELATIONSHIP_TYPES:
        props = RELATIONSHIP_PROPERTIES.get(rt)
        props_str = ", ".join(f"`{p}`" for p in props) if props else "—"
        lines.append(f"| `{rt}` | {props_str} |")

    lines += [
        "",
        "---",
        "",
        "## Assinaturas de aresta",
        "",
        f"Total: **{len(RELATIONSHIP_SIGNATURES)}**",
        "",
        "| Origem | Aresta | Destino |",
        "|---|---|---|",
    ]
    for src, rel, tgt in RELATIONSHIP_SIGNATURES:
        lines.append(f"| `{src}` | `{rel}` | `{tgt}` |")

    live = _try_live_indices()
    if live:
        lines += [
            "",
            "---",
            "",
            "## Indices no banco (live)",
            "",
            "| Label | Propriedades |",
            "|---|---|",
        ]
        lines.extend(live)
    else:
        lines += [
            "",
            "---",
            "",
            "*Banco nao disponivel — schema gerado a partir de `ontology/schema.py` (modo offline).*",
        ]

    lines.append("")
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Schema exportado para {OUTPUT_PATH}")


if __name__ == "__main__":
    export_schema()
