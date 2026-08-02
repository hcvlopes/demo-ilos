"""Testes do modulo de seed comum aos dois setores.

Sao testes offline: validam as constantes e a fixture de normas, nao o
grafo. O que se protege aqui sao as regras invioláveis que este modulo
poderia violar sem que ninguem percebesse — codigo ISO inventado (regra 4),
vocabulario setorial vazando (regra 3) e no exclusivo de um setor (regra 5).
"""

from seed import comum
from seed.generator.fixtures_loader import (
    carregar_modos_falha,
    carregar_normas,
)

TERMOS_PROIBIDOS = ["safra", "silo", "religamento", "colheita", "plantio", "graos"]


class TestCodigosISO:
    """Regra 4: codigo ISO 14224 vem exclusivamente das fixtures."""

    def test_parte_por_modo_so_usa_modos_da_fixture(self):
        validos = {m["codigo"] for m in carregar_modos_falha()}
        usados = set(comum.PARTE_POR_MODO)
        inventados = usados - validos
        assert not inventados, (
            f"PARTE_POR_MODO referencia modos que nao existem em "
            f"fixtures/iso14224/modos_falha.yaml: {sorted(inventados)}"
        )


class TestVocabularioNeutro:
    """Regra 3: vocabulario setorial nunca entra no grafo."""

    def _textos(self):
        for _slug, descricao in comum.PARTE_POR_MODO.values():
            yield descricao
        for c in comum.CONSEQUENCIAS:
            yield c["descricao"]
        for e in comum.ETAPAS_PADRAO:
            yield e["descricao"]
        for n in carregar_normas():
            yield n["descricao"]
            for r in n.get("requisitos", []):
                yield r["descricao"]

    def test_sem_termo_setorial(self):
        for texto in self._textos():
            for termo in TERMOS_PROIBIDOS:
                assert termo not in texto.lower(), (
                    f"Termo setorial '{termo}' em: {texto!r}"
                )


class TestFixtureNormas:
    def test_normas_tem_requisitos(self):
        normas = carregar_normas()
        assert normas, "fixtures/normas.yaml vazio"
        for n in normas:
            assert n["requisitos"], f"Norma {n['codigo']} sem requisito"

    def test_ids_de_requisito_sao_unicos(self):
        vistos = set()
        for n in carregar_normas():
            for r in n["requisitos"]:
                assert r["id"] not in vistos, f"id duplicado: {r['id']}"
                vistos.add(r["id"])

    def test_todo_requisito_tem_criticidade_conhecida(self):
        for n in carregar_normas():
            for r in n["requisitos"]:
                assert r.get("criticidade") in {"alta", "media", "baixa"}, (
                    f"{r['id']} com criticidade invalida: {r.get('criticidade')}"
                )


class TestMaterialSegueCongelado:
    """CLAUDE.md congela Material ate haver cliente real."""

    def test_comum_nao_cria_material(self):
        fonte = (comum.__file__)
        with open(fonte, encoding="utf-8") as f:
            codigo = f.read()
        # Pode ser citado em comentario, mas nunca num MERGE.
        assert "MERGE (m:Material" not in codigo
        assert ":Material {" not in codigo


class TestConsequenciasEEtapas:
    def test_consequencias_tem_severidade(self):
        for c in comum.CONSEQUENCIAS:
            assert c["severidade"] in {"alta", "media", "baixa"}

    def test_etapas_em_ordem_crescente(self):
        ordens = [e["ordem"] for e in comum.ETAPAS_PADRAO]
        assert ordens == sorted(ordens)
        assert len(set(ordens)) == len(ordens), "ordem de etapa duplicada"

    def test_bloqueio_de_energia_e_a_primeira_etapa(self):
        """Sequencia de manutencao comeca por bloqueio — requisito de NR-12."""
        primeira = min(comum.ETAPAS_PADRAO, key=lambda e: e["ordem"])
        assert "bloqueio" in primeira["descricao"].lower()
