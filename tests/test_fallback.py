"""Testes do classificador regex (fallback quando o Ollama nao responde).

O foco aqui e o contrato entre a tabela de regras e as intencoes reais: um
nome de parametro errado na tabela so aparece em producao como HTTP 500,
porque a ValidationError acontece na hora de tipar os parametros. Os testes
de coerencia abaixo pegam isso no CI.
"""

import inspect

import pytest

from api.orquestrador import _REGRAS_FALLBACK, _classificar_fallback
from intents.registry import REGISTRY, get_intencao


def _tipo_params(nome: str):
    """Modelo Pydantic de parametros declarado pela intencao."""
    inst = get_intencao(nome)
    sig = inspect.signature(type(inst).executar)
    return list(sig.parameters.values())[2].annotation


class TestCoerenciaDaTabela:
    """A tabela de regras precisa casar com as intencoes de verdade."""

    @pytest.mark.parametrize(
        ("intencao", "param_key"),
        [(regra[1], regra[2]) for regra in _REGRAS_FALLBACK],
    )
    def test_intencao_existe_no_registry(self, intencao, param_key):
        assert intencao in REGISTRY, f"Regra aponta para intencao inexistente: {intencao}"

    @pytest.mark.parametrize(
        ("intencao", "param_key"),
        [(regra[1], regra[2]) for regra in _REGRAS_FALLBACK if regra[2]],
    )
    def test_param_existe_na_intencao(self, intencao, param_key):
        campos = set(_tipo_params(intencao).model_fields.keys())
        assert param_key in campos, (
            f"Regra de '{intencao}' preenche '{param_key}', "
            f"mas a intencao declara {sorted(campos)}"
        )

    @pytest.mark.parametrize(
        "intencao",
        [regra[1] for regra in _REGRAS_FALLBACK if regra[2] is None],
    )
    def test_intencao_sem_param_nao_tem_campo_obrigatorio(self, intencao):
        """Regra sem param_key so pode apontar para intencao sem campo exigido."""
        obrigatorios = [
            n for n, f in _tipo_params(intencao).model_fields.items() if f.is_required()
        ]
        assert not obrigatorios, (
            f"Regra de '{intencao}' nao preenche parametro, "
            f"mas a intencao exige {obrigatorios}"
        )

    def test_toda_classificacao_produz_params_tipaveis(self):
        """O que o fallback devolve tem que sobreviver a tipagem da intencao.

        Este e o teste que teria pego o bug de acoes_permitidas: a regra
        preenchia equipamento_id numa intencao que exige defeito_id.
        """
        for _pattern, intencao, param_key, _extrator in _REGRAS_FALLBACK:
            parametros = {param_key: "XX-000"} if param_key else {}
            PT = _tipo_params(intencao)
            PT(**parametros)  # levanta ValidationError se a regra estiver errada


class TestExtracaoDeId:
    """IDs compostos precisam ser capturados inteiros."""

    @pytest.mark.parametrize(
        ("pergunta", "esperado"),
        [
            ("me explique o defeito DEF-001", "DEF-001"),
            ("qual o impacto de parada do ativo ATV-PRT-01?", "ATV-PRT-01"),
            ("historico do equipamento EQ-TRE-001", "EQ-TRE-001"),
            ("resumo do sistema SIS-PRT", "SIS-PRT"),
            ("resumo da edificacao EDIF-001", "EDIF-001"),
            ("ativos em risco no processo PO-001", "PO-001"),
        ],
    )
    def test_captura_id_completo(self, pergunta, esperado):
        c = _classificar_fallback(pergunta)
        assert c.intencao != "desconhecida", f"nao classificou: {pergunta}"
        assert esperado in c.parametros.values(), (
            f"esperava {esperado}, veio {c.parametros}"
        )

    def test_id_composto_nao_e_truncado(self):
        """ATV-PRT-01 nao pode virar PRT-01."""
        c = _classificar_fallback("dependencias do ativo ATV-PRT-01")
        assert c.parametros["ativo_id"] == "ATV-PRT-01"


class TestForaDeEscopo:
    def test_pergunta_sem_relacao_e_desconhecida(self):
        assert _classificar_fallback("qual a capital da Franca?").intencao == "desconhecida"

    def test_pergunta_vazia_e_desconhecida(self):
        assert _classificar_fallback("").intencao == "desconhecida"


# Corpus de perguntas reais, uma linha por formulacao esperada. E o teste que
# mede de verdade a cobertura do fallback: sem ele, "melhorar os padroes" e
# opiniao. Cada entrada e (pergunta, intencao_esperada).
CORPUS = [
    # conformidade_normativa
    ("quais equipamentos estao sujeitos a NR-12?", "conformidade_normativa"),
    ("que equipamentos a NR 12 alcanca", "conformidade_normativa"),
    ("o que a ISO 14224 exige?", "conformidade_normativa"),
    ("quais requisitos a NBR 5410 impoe", "conformidade_normativa"),
    ("qual a abrangencia da NR-12", "conformidade_normativa"),

    # requisitos_equipamento
    ("quais requisitos incidem sobre o EQ-TRE-001?", "requisitos_equipamento"),
    ("que requisitos normativos se aplicam ao equipamento EQ-MOE-001", "requisitos_equipamento"),

    # normas_aplicaveis
    ("quais normas se aplicam ao EQ-TRE-001?", "normas_aplicaveis"),
    ("que norma regulamenta o EQ-SEC-001", "normas_aplicaveis"),

    # acoes_por_papel
    ("o que um tecnico pode fazer?", "acoes_por_papel"),
    ("que acoes o supervisor esta autorizado a executar", "acoes_por_papel"),
    ("quem pode autorizar uma substituicao?", "acoes_por_papel"),
    ("quais papeis existem", "acoes_por_papel"),

    # acoes_permitidas
    ("quais acoes sao permitidas para o defeito DEF-001?", "acoes_permitidas"),
    ("que acao posso tomar no DEF-002", "acoes_permitidas"),

    # defeitos_resolvidos
    ("quais defeitos ja foram resolvidos?", "defeitos_resolvidos"),
    ("me mostre os defeitos encerrados", "defeitos_resolvidos"),
    ("defeitos fechados recentemente", "defeitos_resolvidos"),

    # defeitos_abertos
    ("quais defeitos estao abertos?", "defeitos_abertos"),
    ("liste os defeitos em aberto", "defeitos_abertos"),
    ("tem defeito pendente?", "defeitos_abertos"),

    # cadeia_falha
    ("mostre a cadeia de falha do DEF-901", "cadeia_falha"),
    ("qual a cadeia de falha do defeito DEF-001", "cadeia_falha"),

    # localizacao_defeito
    ("qual a peca afetada pelo DEF-001?", "localizacao_defeito"),
    ("onde esta o defeito DEF-002", "localizacao_defeito"),
    ("que componente falhou no DEF-003", "localizacao_defeito"),

    # etapas_ordem
    ("quais as etapas da ordem OM-DEF-901?", "etapas_ordem"),
    ("quem executa a OM-DEF-902", "etapas_ordem"),

    # plano_manutencao_ativo
    ("qual o plano de manutencao do ATV-PRT-01?", "plano_manutencao_ativo"),
    ("que lista de tarefa cobre o ATV-ARM-01", "plano_manutencao_ativo"),

    # ordens_manutencao
    ("quais ordens de manutencao do EQ-TRE-001?", "ordens_manutencao"),

    # consequencia_notas
    ("qual a consequencia das notas do EQ-TRE-001?", "consequencia_notas"),
    ("qual a severidade das notas do EQ-MOE-001", "consequencia_notas"),

    # carga_centro_trabalho
    ("qual a carga do centro de manutencao CT-MNT-001?", "carga_centro_trabalho"),
    ("quantos equipamentos o centro de trabalho atende", "carga_centro_trabalho"),

    # escopo_grupo_planejamento
    ("qual o escopo do grupo de planejamento GPJ-001?", "escopo_grupo_planejamento"),
    ("o que o planejamento central cobre", "escopo_grupo_planejamento"),

    # ranking_sistemas
    ("qual o pior sistema em confiabilidade?", "ranking_sistemas"),
    ("compare os sistemas por taxa de falha", "ranking_sistemas"),
    ("qual sistema e menos confiavel", "ranking_sistemas"),

    # ativos_em_risco_por_processo
    ("quais ativos estao em risco no processo PO-001?", "ativos_em_risco_por_processo"),
    ("qual o escore de risco do PO-002", "ativos_em_risco_por_processo"),

    # explicar_defeito
    ("me explique o defeito DEF-001", "explicar_defeito"),
    ("detalhe o defeito DEF-002", "explicar_defeito"),

    # explicar_processo
    ("explique o processo PO-001", "explicar_processo"),
    ("que indicador mede o PO-001", "explicar_processo"),

    # listar_equipamentos_ativo
    ("liste os equipamentos do ATV-PRT-01", "listar_equipamentos_ativo"),
    ("que equipamentos compoe o ativo ATV-REC-01", "listar_equipamentos_ativo"),

    # resumo_sistema / resumo_edificacao
    ("resumo do sistema SIS-PRT", "resumo_sistema"),
    ("resumo da edificacao EDIF-001", "resumo_edificacao"),

    # dependencias_ativo
    ("quais as dependencias do ATV-PRT-01?", "dependencias_ativo"),
    ("do que depende o ATV-EXP-01", "dependencias_ativo"),

    # impacto_parada
    ("qual o impacto de parada do ATV-PRT-01?", "impacto_parada"),
    ("o que acontece se o ATV-ARM-01 parar", "impacto_parada"),

    # monitoramento_equipamento
    ("qual o monitoramento do EQ-TRE-001?", "monitoramento_equipamento"),
    ("mostre a tendencia do sensor no EQ-TRE-001", "monitoramento_equipamento"),

    # estatisticas_classe
    ("qual a taxa de falha da classe CT-BCC?", "estatisticas_classe"),
    ("estatisticas da classe CT-MOE", "estatisticas_classe"),

    # historico_equipamento
    ("qual o historico do EQ-TRE-001?", "historico_equipamento"),
    ("o EQ-MOE-001 ja falhou antes", "historico_equipamento"),
]


class TestCorpusDeFormulacoes:
    """Cobertura do fallback sobre formulacoes naturais em pt-BR."""

    @pytest.mark.parametrize(("pergunta", "esperada"), CORPUS)
    def test_classifica_como_esperado(self, pergunta, esperada):
        c = _classificar_fallback(pergunta)
        assert c.intencao == esperada, (
            f"{pergunta!r}\n  esperava {esperada}, veio {c.intencao} ({c.parametros})"
        )

    @pytest.mark.parametrize(("pergunta", "esperada"), CORPUS)
    def test_parametros_sobrevivem_a_tipagem(self, pergunta, esperada):
        """Nao basta classificar: os parametros tem que tipar sem ValidationError."""
        c = _classificar_fallback(pergunta)
        _tipo_params(c.intencao)(**c.parametros)

    def test_corpus_cobre_toda_intencao_alcancavel(self):
        """Toda intencao que o fallback sabe produzir aparece no corpus."""
        alcancaveis = {r[1] for r in _REGRAS_FALLBACK}
        no_corpus = {esperada for _p, esperada in CORPUS}
        assert alcancaveis <= no_corpus, (
            f"Intencoes sem formulacao no corpus: {sorted(alcancaveis - no_corpus)}"
        )


class TestNormalizacaoDeNorma:
    """O codigo da norma tem que sair na forma gravada no grafo."""

    @pytest.mark.parametrize(
        ("pergunta", "esperado"),
        [
            ("equipamentos sujeitos a NR-12", "NR-12"),
            ("equipamentos sujeitos a NR 12", "NR-12"),
            ("equipamentos sujeitos a nr12", "NR-12"),
            ("o que a NBR 5410 exige", "NBR 5410"),
            ("o que a ISO 14224 exige", "ISO 14224:2016"),
        ],
    )
    def test_normaliza_codigo(self, pergunta, esperado):
        c = _classificar_fallback(pergunta)
        assert c.intencao == "conformidade_normativa"
        assert c.parametros["norma_id"] == esperado


class TestPapelPorNome:
    @pytest.mark.parametrize(
        ("pergunta", "esperado"),
        [
            ("o que um tecnico pode fazer", "PAPEL-TEC"),
            ("o que o supervisor pode autorizar", "PAPEL-SUP"),
            ("o que o engenheiro pode executar", "PAPEL-ENG"),
        ],
    )
    def test_mapeia_nome_para_id(self, pergunta, esperado):
        c = _classificar_fallback(pergunta)
        assert c.intencao == "acoes_por_papel"
        assert c.parametros["papel_id"] == esperado
