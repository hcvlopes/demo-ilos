"""Testes da consulta livre — o caminho em que o LLM escreve o Cypher.

Este e o modulo que rompe a regra original do projeto, entao e o que mais
precisa de teste. O foco nao e o caminho feliz: e provar que escrita nao
passa, que o Cypher fica visivel, e que a resposta se declara menos confiavel
do que a de uma intencao versionada.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from api.consulta_livre import (
    LIMITE_PADRAO,
    ConsultaRecusada,
    _prompt_sistema,
    descrever_schema,
    executar_consulta_livre,
    gerar_cypher,
    validar_cypher,
)
from api.orquestrador import criar_cliente_ollama
from ontology.schema import NODE_LABELS


class TestGuardaSomenteLeitura:
    """Nenhuma clausula de escrita pode passar pela guarda sintatica."""

    @pytest.mark.parametrize(
        "travessia",
        [
            "MATCH (n) DETACH DELETE n",
            "CREATE (x:Teste {id:'x'}) RETURN x",
            "MATCH (n:Norma) SET n.codigo = 'HACK' RETURN n",
            "MATCH (n) REMOVE n.descricao RETURN n",
            "MERGE (x:Teste {id:'x'}) RETURN x",
            "DROP INDEX ON :Norma(id)",
            "LOAD CSV FROM 'http://x' AS l RETURN l",
            "MATCH (n) FOREACH (x IN [1] | SET n.a = 1) RETURN n",
            "CALL db.labels()",
            "CALL dbms.components()",
            "MATCH (n) WITH n CALL { WITH n CREATE (:X) } RETURN n",
        ],
    )
    def test_recusa_escrita_e_procedimento(self, travessia):
        with pytest.raises(ConsultaRecusada):
            validar_cypher(travessia)

    def test_clausula_escondida_em_comentario_de_linha_e_pega(self):
        """Comentario nao pode ser usado para disfarcar o que executa."""
        with pytest.raises(ConsultaRecusada):
            validar_cypher("MATCH (n) //nada aqui\n DETACH DELETE n")

    def test_clausula_escondida_em_bloco_e_pega(self):
        with pytest.raises(ConsultaRecusada):
            validar_cypher("MATCH (n) /* disfarce */ DELETE n")

    def test_clausula_dentro_de_comentario_nao_e_falso_positivo(self):
        """O DELETE aqui esta comentado e nao executa — recusar seria errado."""
        saida = validar_cypher("MATCH (n) /* antes tinha DELETE n */ RETURN n LIMIT 5")
        assert "RETURN n" in saida

    def test_propriedade_com_nome_parecido_nao_e_bloqueada(self):
        """`setor` contem 'set'; a fronteira de palavra evita o falso positivo."""
        saida = validar_cypher(
            "MATCH (e:Equipamento) WHERE e.setor = 'x' RETURN e LIMIT 5",
        )
        assert "setor" in saida

    def test_exige_inicio_de_leitura(self):
        with pytest.raises(ConsultaRecusada):
            validar_cypher("EXPLAIN MATCH (n) RETURN n")

    def test_consulta_vazia_e_recusada(self):
        with pytest.raises(ConsultaRecusada):
            validar_cypher("   ")


class TestLimite:
    def test_acrescenta_limit_quando_falta(self):
        saida = validar_cypher("MATCH (n:Norma) RETURN n")
        assert f"LIMIT {LIMITE_PADRAO}" in saida

    def test_respeita_limit_existente(self):
        saida = validar_cypher("MATCH (n:Norma) RETURN n LIMIT 3")
        assert saida.count("LIMIT") == 1
        assert "LIMIT 3" in saida


class TestSchemaNoPrompt:
    def test_descreve_todos_os_rotulos(self):
        schema = descrever_schema()
        for label in NODE_LABELS:
            assert label in schema

    def test_prompt_proibe_escrita_e_exige_limit(self):
        prompt = _prompt_sistema()
        assert "Somente leitura" in prompt
        assert "LIMIT" in prompt
        assert "Nao invente rotulo" in prompt


class _StubCypher(BaseHTTPRequestHandler):
    resposta: ClassVar[str] = '{"cypher": "MATCH (n:Norma) RETURN n.codigo AS codigo", "motivo": ""}'

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        corpo = json.dumps({
            "model": "llama3.1",
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": type(self).resposta},
            "done": True,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def stub_cypher():
    _StubCypher.resposta = (
        '{"cypher": "MATCH (n:Norma) RETURN n.codigo AS codigo", "motivo": ""}'
    )
    servidor = HTTPServer(("127.0.0.1", 0), _StubCypher)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{servidor.server_port}", _StubCypher
    finally:
        servidor.shutdown()
        servidor.server_close()


class TestGeracao:
    def test_gera_e_valida(self, stub_cypher):
        host, _ = stub_cypher
        travessia, motivo = gerar_cypher("quais normas existem", criar_cliente_ollama(host))
        assert motivo == ""
        assert travessia.startswith("MATCH")
        assert "LIMIT" in travessia

    def test_escrita_gerada_pelo_llm_e_recusada(self, stub_cypher):
        """Se o modelo desobedecer o prompt, a guarda pega antes do banco."""
        host, stub = stub_cypher
        stub.resposta = '{"cypher": "MATCH (n) DETACH DELETE n", "motivo": ""}'
        with pytest.raises(ConsultaRecusada):
            gerar_cypher("apague tudo", criar_cliente_ollama(host))

    def test_modelo_declara_que_nao_consegue(self, stub_cypher):
        host, stub = stub_cypher
        stub.resposta = '{"cypher": "", "motivo": "schema nao cobre previsao do tempo"}'
        travessia, motivo = gerar_cypher("vai chover?", criar_cliente_ollama(host))
        assert travessia == ""
        assert "previsao" in motivo


class _SessaoFalsa:
    """Sessao que so aceita leitura, como o RO_QUERY do servidor."""

    def __init__(self, linhas, colunas):
        self.linhas, self.colunas = linhas, colunas
        self.executou = None

    def run_somente_leitura(self, travessia, parameters=None):
        self.executou = travessia
        colunas = self.colunas

        class Reg(dict):
            def keys(self):
                return colunas

        return [Reg(dict(zip(colunas, linha, strict=False))) for linha in self.linhas]


class TestEnvelopeDaConsultaLivre:
    def test_declara_a_menor_confianca_em_lacuna(self, stub_cypher):
        host, _ = stub_cypher
        sessao = _SessaoFalsa([["NR-12"], ["ISO 14224:2016"]], ["codigo"])

        envelope, _travessia = executar_consulta_livre(
            "quais normas existem", sessao, client=criar_cliente_ollama(host),
        )

        assert any("nao por intencao versionada" in x for x in envelope.lacunas)
        assert any("revisao nem por teste" in x for x in envelope.lacunas)

    def test_devolve_o_cypher_para_auditoria(self, stub_cypher):
        host, _ = stub_cypher
        sessao = _SessaoFalsa([["NR-12"]], ["codigo"])

        _envelope, travessia = executar_consulta_livre(
            "quais normas existem", sessao, client=criar_cliente_ollama(host),
        )

        assert "MATCH (n:Norma)" in travessia
        assert travessia == sessao.executou

    def test_usa_a_sessao_somente_leitura(self, stub_cypher):
        """Nao pode cair no session.run() comum, que aceita escrita."""
        host, _ = stub_cypher

        class SoLeituraProibida:
            def run(self, *a, **k):
                raise AssertionError("consulta livre nao pode usar session.run()")

            def run_somente_leitura(self, travessia, parameters=None):
                return []

        executar_consulta_livre(
            "quais normas existem", SoLeituraProibida(),
            client=criar_cliente_ollama(host),
        )

    def test_resultado_vazio_vira_lacuna_e_nao_erro(self, stub_cypher):
        host, _ = stub_cypher
        envelope, _ = executar_consulta_livre(
            "quais normas existem", _SessaoFalsa([], ["codigo"]),
            client=criar_cliente_ollama(host),
        )
        assert any("nao retornou nenhuma linha" in x for x in envelope.lacunas)

    def test_truncamento_e_declarado(self, stub_cypher):
        host, _ = stub_cypher
        linhas = [[f"N-{i}"] for i in range(LIMITE_PADRAO)]
        envelope, _ = executar_consulta_livre(
            "quais normas existem", _SessaoFalsa(linhas, ["codigo"]),
            client=criar_cliente_ollama(host),
        )
        assert any("truncado" in x for x in envelope.lacunas)

    def test_envelope_tem_os_seis_campos(self, stub_cypher):
        """Regra 2 vale tambem para a consulta livre."""
        host, _ = stub_cypher
        envelope, _ = executar_consulta_livre(
            "quais normas existem", _SessaoFalsa([["NR-12"]], ["codigo"]),
            client=criar_cliente_ollama(host),
        )
        for campo in ["afirmacao", "nos", "arestas", "calculos", "normas", "lacunas"]:
            assert hasattr(envelope, campo)
        assert envelope.afirmacao


class TestLLMIndisponivel:
    """Sem Ollama, pergunta fora do catalogo nao pode virar 500.

    O caminho de intencao continua funcionando sem LLM (fallback regex). Se a
    consulta livre deixasse subir o ConnectionError cru, a pergunta fora do
    catalogo devolveria erro de conexao em vez de dizer o que fazer — e no
    palco isso aconteceria justamente quando o Ollama engasgasse.
    """

    def test_falha_de_conexao_vira_consulta_recusada(self):
        client = criar_cliente_ollama("http://127.0.0.1:1")
        with pytest.raises(ConsultaRecusada) as exc:
            gerar_cypher("quantos equipamentos por fabricante", client)
        mensagem = str(exc.value)
        assert "consulta livre precisa do LLM" in mensagem
        assert "make llm-check" in mensagem

    def test_json_invalido_do_gerador_vira_consulta_recusada(self, stub_cypher):
        host, stub = stub_cypher
        stub.resposta = "isso nao e json"
        with pytest.raises(ConsultaRecusada, match="JSON valido"):
            gerar_cypher("qualquer coisa", criar_cliente_ollama(host))
