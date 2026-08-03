"""Testes do corpus de exemplos.

Offline: nao tocam o grafo. O que se valida aqui e o que da para validar sem
banco — sintaxe, guarda, rotulos da ontologia, cobertura de categoria e a
selecao few-shot. A execucao de verdade e `make exemplos-validar`, que exige
o grafo semeado.
"""

import pytest

from api.consulta_livre import validar_cypher
from api.exemplos import (
    ExemploConsulta,
    _normalizar,
    carregar_exemplos,
    categorias,
    formatar_para_prompt,
    selecionar,
)
from ontology.schema import NODE_LABELS, RELATIONSHIP_TYPES

CORPUS = carregar_exemplos()


class TestCorpus:
    def test_corpus_e_grande(self):
        assert len(CORPUS) >= 40, f"apenas {len(CORPUS)} exemplos"

    def test_perguntas_sao_unicas(self):
        perguntas = [e.pergunta for e in CORPUS]
        assert len(perguntas) == len(set(perguntas))

    def test_cobre_todas_as_categorias_previstas(self):
        esperadas = {
            "hierarquia", "defeitos", "confiabilidade", "normas",
            "manutencao", "operacao", "organizacao", "cruzadas",
        }
        assert esperadas <= categorias(), f"faltam: {esperadas - categorias()}"

    def test_toda_categoria_tem_ao_menos_tres_exemplos(self):
        contagem = {}
        for e in CORPUS:
            contagem[e.categoria] = contagem.get(e.categoria, 0) + 1
        magras = {c: n for c, n in contagem.items() if n < 3}
        assert not magras, f"categorias com poucos exemplos: {magras}"


class TestExemplosPassamNaGuarda:
    """Exemplo que a propria guarda recusaria ensinaria o modelo a errar."""

    @pytest.mark.parametrize("exemplo", CORPUS, ids=lambda e: e.pergunta[:40])
    def test_passa_na_guarda_somente_leitura(self, exemplo):
        validar_cypher(exemplo.cypher)

    @pytest.mark.parametrize("exemplo", CORPUS, ids=lambda e: e.pergunta[:40])
    def test_tem_limit(self, exemplo):
        assert "limit" in exemplo.cypher.lower()

    @pytest.mark.parametrize("exemplo", CORPUS, ids=lambda e: e.pergunta[:40])
    def test_nomeia_as_colunas(self, exemplo):
        """`AS` em toda coluna: o modelo copia o estilo, e coluna sem nome
        deixa a narracao sem palavra para usar."""
        assert " AS " in exemplo.cypher, exemplo.cypher


class TestExemplosUsamOSchemaReal:
    """Rotulo ou relacao inventada no exemplo vira alucinacao no modelo."""

    @pytest.mark.parametrize("exemplo", CORPUS, ids=lambda e: e.pergunta[:40])
    def test_so_usa_rotulos_da_ontologia(self, exemplo):
        import re

        usados = set(re.findall(r"[:\(]\s*\w*\s*:([A-Z]\w+)", exemplo.cypher))
        invalidos = usados - set(NODE_LABELS)
        assert not invalidos, f"rotulos fora da ontologia: {invalidos}"

    @pytest.mark.parametrize("exemplo", CORPUS, ids=lambda e: e.pergunta[:40])
    def test_so_usa_relacoes_da_ontologia(self, exemplo):
        import re

        usadas = set(re.findall(r"\[\s*\w*\s*:([A-Z_]+)\s*\]", exemplo.cypher))
        invalidas = usadas - set(RELATIONSHIP_TYPES)
        assert not invalidas, f"relacoes fora da ontologia: {invalidas}"


class TestSelecaoFewShot:
    def test_escolhe_o_exemplo_identico_primeiro(self):
        alvo = CORPUS[0]
        escolhidos = selecionar(alvo.pergunta, quantos=3)
        assert escolhidos[0].pergunta == alvo.pergunta

    def test_prioriza_o_tema_da_pergunta(self):
        escolhidos = selecionar("quantos defeitos estao abertos hoje?", quantos=4)
        assert any("defeito" in e.pergunta.lower() for e in escolhidos)

    def test_respeita_o_limite(self):
        assert len(selecionar("equipamentos", quantos=3)) <= 3

    def test_pergunta_sem_relacao_ainda_devolve_exemplos(self):
        """Melhor mostrar o estilo esperado do que nao mostrar nada."""
        escolhidos = selecionar("xyzzy plugh", quantos=5)
        assert len(escolhidos) == 5

    def test_ignora_acento_e_caixa(self):
        com = selecionar("Quais NORMAS existem?", quantos=3)
        sem = selecionar("quais normas existem", quantos=3)
        assert [e.pergunta for e in com] == [e.pergunta for e in sem]

    def test_descarta_palavra_vazia(self):
        assert _normalizar("quais sao os equipamentos") == {"equipamentos"}


class TestFormatacaoDoPrompt:
    def test_inclui_pergunta_e_cypher(self):
        texto = formatar_para_prompt([
            ExemploConsulta("P?", "MATCH (n) RETURN n LIMIT 1", "teste"),
        ])
        assert "Pergunta: P?" in texto
        assert "MATCH (n) RETURN n LIMIT 1" in texto

    def test_lista_vazia_nao_produz_cabecalho_solto(self):
        assert formatar_para_prompt([]) == ""


class TestPromptComExemplos:
    def test_prompt_carrega_exemplos_relevantes(self):
        from api.consulta_livre import _prompt_sistema

        prompt = _prompt_sistema("quantos equipamentos cada fabricante fornece?")
        assert "Exemplos de consultas corretas" in prompt
        assert "Fabricante" in prompt

    def test_prompt_sem_pergunta_nao_traz_exemplo(self):
        """Chamado sem pergunta (introspeccao, teste), so o schema."""
        from api.consulta_livre import _prompt_sistema

        assert "Exemplos de consultas corretas" not in _prompt_sistema()

    def test_prompt_nao_estoura_de_tamanho(self):
        """Few-shot ajuda ate o ponto em que rouba contexto do raciocinio."""
        from api.consulta_livre import _prompt_sistema

        prompt = _prompt_sistema("quais defeitos estao abertos no sistema de secagem?")
        assert len(prompt) < 12000, f"prompt com {len(prompt)} chars"


class TestExportacaoJSONL:
    def test_exporta_no_formato_de_mensagens(self, tmp_path):
        import json

        from scripts.validar_exemplos import exportar_jsonl

        destino = tmp_path / "treino.jsonl"
        exportar_jsonl(str(destino))
        linhas = destino.read_text(encoding="utf-8").strip().split("\n")
        assert len(linhas) == len(CORPUS)

        registro = json.loads(linhas[0])
        papeis = [m["role"] for m in registro["messages"]]
        assert papeis == ["system", "user", "assistant"]
        resposta = json.loads(registro["messages"][2]["content"])
        assert "cypher" in resposta
        assert registro["categoria"]
