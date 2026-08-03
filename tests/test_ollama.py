"""Testes do caminho LLM (Ollama) do orquestrador.

Sobem um servidor HTTP local que fala a API do Ollama (`/api/chat`,
`/api/tags`) e exercitam o cliente `ollama` de verdade. Nao ha rede externa
nem modelo baixado — o que se valida e o contrato: como o orquestrador monta
a requisicao, interpreta a resposta e degrada para o classificador regex
quando o LLM falha.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from api.orquestrador import (
    ClassificacaoIntencao,
    _construir_prompt_sistema,
    classificar_intencao,
    criar_cliente_ollama,
    verificar_ollama,
)
from intents.registry import REGISTRY


class _StubOllama(BaseHTTPRequestHandler):
    """Servidor minimo que imita as rotas do Ollama usadas pelo projeto."""

    resposta_chat: ClassVar[str] = (
        '{"intencao": "explicar_defeito", "parametros": {"defeito_id": "DEF-001"}}'
    )
    modelos: ClassVar[list[str]] = ["llama3.1:latest"]
    status_chat: ClassVar[int] = 200
    ultimo_payload: ClassVar[dict | None] = None

    def log_message(self, *args):
        pass

    def _json(self, status, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        if self.path == "/api/tags":
            self._json(200, {
                "models": [
                    {
                        "name": m,
                        "model": m,
                        "modified_at": "2026-01-01T00:00:00Z",
                        "size": 1,
                        "digest": "0" * 64,
                        "details": {
                            "parent_model": "",
                            "format": "gguf",
                            "family": "llama",
                            "families": ["llama"],
                            "parameter_size": "8B",
                            "quantization_level": "Q4_0",
                        },
                    }
                    for m in type(self).modelos
                ],
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        bruto = self.rfile.read(tamanho)
        type(self).ultimo_payload = json.loads(bruto) if bruto else {}

        if self.path != "/api/chat":
            self._json(404, {"error": "not found"})
            return

        if type(self).status_chat != 200:
            self._json(type(self).status_chat, {"error": "boom"})
            return

        self._json(200, {
            "model": type(self).ultimo_payload.get("model", "llama3.1"),
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": type(self).resposta_chat},
            "done": True,
            "done_reason": "stop",
        })


@pytest.fixture
def stub_ollama():
    """Sobe o stub numa porta livre e devolve (host, classe do handler)."""
    _StubOllama.resposta_chat = (
        '{"intencao": "explicar_defeito", "parametros": {"defeito_id": "DEF-001"}}'
    )
    _StubOllama.modelos = ["llama3.1:latest"]
    _StubOllama.status_chat = 200
    _StubOllama.ultimo_payload = None

    servidor = HTTPServer(("127.0.0.1", 0), _StubOllama)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    host = f"http://127.0.0.1:{servidor.server_port}"
    try:
        yield host, _StubOllama
    finally:
        servidor.shutdown()
        servidor.server_close()


class TestClassificacaoViaLLM:
    """Caminho feliz: o Ollama responde e o orquestrador usa a resposta."""

    def test_usa_resposta_do_llm(self, stub_ollama):
        host, _ = stub_ollama
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "llm"
        assert c.motivo_fallback is None
        assert c.intencao == "explicar_defeito"
        assert c.parametros == {"defeito_id": "DEF-001"}

    def test_envia_prompt_de_sistema_e_pergunta(self, stub_ollama):
        host, stub = stub_ollama
        client = criar_cliente_ollama(host)

        classificar_intencao("me explique o defeito DEF-001", client=client)

        payload = stub.ultimo_payload
        assert payload["format"] == "json"
        papeis = [m["role"] for m in payload["messages"]]
        assert papeis == ["system", "user"]
        assert payload["messages"][1]["content"] == "me explique o defeito DEF-001"
        for nome in REGISTRY:
            assert nome in payload["messages"][0]["content"]

    def test_llm_vence_o_regex(self, stub_ollama):
        """Pergunta que o regex classificaria diferente do que o LLM devolveu."""
        host, stub = stub_ollama
        stub.resposta_chat = (
            '{"intencao": "historico_equipamento", "parametros": {"equipamento_id": "EQ-TRE-001"}}'
        )
        client = criar_cliente_ollama(host)

        c = classificar_intencao("quais defeitos estao abertos?", client=client)

        assert c.origem == "llm"
        assert c.intencao == "historico_equipamento"

    def test_aceita_json_em_bloco_de_codigo(self, stub_ollama):
        host, stub = stub_ollama
        stub.resposta_chat = (
            '```json\n{"intencao": "defeitos_abertos", "parametros": {}}\n```'
        )
        client = criar_cliente_ollama(host)

        c = classificar_intencao("liste os defeitos", client=client)

        assert c.origem == "llm"
        assert c.intencao == "defeitos_abertos"


class TestDegradacaoParaRegex:
    """A queda para o classificador regex nunca e silenciosa."""

    def test_servidor_fora_do_ar(self):
        client = criar_cliente_ollama("http://127.0.0.1:1")

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "fallback"
        assert c.motivo_fallback
        assert c.intencao == "explicar_defeito"

    def test_erro_http_do_servidor(self, stub_ollama):
        host, stub = stub_ollama
        stub.status_chat = 500
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "fallback"
        assert c.motivo_fallback

    def test_json_invalido_do_llm(self, stub_ollama):
        host, stub = stub_ollama
        stub.resposta_chat = "isso nao e json"
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "fallback"
        assert "JSON invalido" in c.motivo_fallback
        assert c.intencao == "explicar_defeito"

    def test_llm_inventa_intencao_inexistente(self, stub_ollama):
        """Alucinacao de intencao nao pode virar KeyError na execucao."""
        host, stub = stub_ollama
        stub.resposta_chat = '{"intencao": "deletar_tudo", "parametros": {}}'
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "fallback"
        assert "inexistente" in c.motivo_fallback
        assert c.intencao in REGISTRY or c.intencao == "desconhecida"

    def test_pergunta_fora_de_escopo_sem_llm(self):
        client = criar_cliente_ollama("http://127.0.0.1:1")

        c = classificar_intencao("qual a capital da Franca?", client=client)

        assert c.origem == "fallback"
        assert c.intencao == "desconhecida"


class TestVerificarOllama:
    """Diagnostico exposto pelo /saude."""

    def test_servidor_com_modelo(self, stub_ollama):
        host, _ = stub_ollama
        client = criar_cliente_ollama(host)

        info = verificar_ollama(client=client, modelo="llama3.1")

        assert info["disponivel"] is True
        assert "llama3.1:latest" in info["modelos_disponiveis"]

    def test_servidor_sem_o_modelo_pedido(self, stub_ollama):
        host, stub = stub_ollama
        stub.modelos = ["qwen2.5:latest"]
        client = criar_cliente_ollama(host)

        info = verificar_ollama(client=client, modelo="llama3.1")

        assert info["disponivel"] is False
        assert "ollama pull llama3.1" in info["detalhe"]

    def test_servidor_inacessivel(self):
        client = criar_cliente_ollama("http://127.0.0.1:1")

        info = verificar_ollama(client=client, modelo="llama3.1")

        assert info["disponivel"] is False
        assert "inacessivel" in info["detalhe"]


class TestContratoDeSeguranca:
    """A regra inviolavel: o LLM nunca escreve Cypher."""

    def test_cypher_injetado_pelo_llm_nao_sobrevive_a_classificacao(self, stub_ollama):
        """Se o LLM devolver uma query, ela nao passa da classificacao.

        A barreira e dupla e este teste cobre as duas. A saneadora descarta
        toda chave que a intencao nao declara, entao o Cypher nem chega ao
        resultado da classificacao; e mesmo se chegasse, a tipagem Pydantic
        nao o carregaria adiante.
        """
        host, stub = stub_ollama
        stub.resposta_chat = json.dumps({
            "intencao": "explicar_defeito",
            "parametros": {"defeito_id": "DEF-001", "query": "MATCH (n) DETACH DELETE n"},
        })
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        # Primeira barreira: a chave nao declarada some na saneadora.
        assert "query" not in c.parametros
        assert c.parametros == {"defeito_id": "DEF-001"}

        # Segunda barreira: mesmo forcando a query de volta, a tipagem descarta.
        from api.orquestrador import tipo_de_params

        param_type = tipo_de_params(c.intencao)
        tipados = param_type(defeito_id="DEF-001", query="MATCH (n) DETACH DELETE n")
        assert not hasattr(tipados, "query")
        assert tipados.model_dump() == {"defeito_id": "DEF-001"}

    def test_classificacao_tem_apenas_campos_declarados(self):
        campos = set(ClassificacaoIntencao.model_fields.keys())
        assert campos == {"intencao", "parametros", "origem", "motivo_fallback"}


class TestParametrosInvalidosDoLLM:
    """Parametro que nao tipa nao pode virar 500 na cara do usuario.

    O caso real: perguntado "O que a ISO 14224 exige?", o llama3.1 respondeu
    `requisitos_equipamento` com `equipamento_id: null`. Isso estourava
    ValidationError na execucao e chegava a tela como um dump do pydantic.
    """

    def test_param_nulo_degrada_para_regex(self, stub_ollama):
        host, stub = stub_ollama
        stub.resposta_chat = (
            '{"intencao": "requisitos_equipamento", "parametros": {"equipamento_id": null}}'
        )
        client = criar_cliente_ollama(host)

        c = classificar_intencao("O que a ISO 14224 exige?", client=client)

        assert c.origem == "fallback"
        assert "equipamento_id" in c.motivo_fallback
        # E o regex acerta a intencao que o LLM errou.
        assert c.intencao == "conformidade_normativa"
        assert c.parametros["norma_id"] == "ISO 14224:2016"

    def test_param_obrigatorio_ausente_degrada(self, stub_ollama):
        host, stub = stub_ollama
        stub.resposta_chat = '{"intencao": "explicar_defeito", "parametros": {}}'
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "fallback"
        assert c.intencao == "explicar_defeito"
        assert c.parametros["defeito_id"] == "DEF-001"

    def test_chave_inventada_e_descartada(self, stub_ollama):
        """Parametro que a intencao nao declara nao impede a classificacao."""
        host, stub = stub_ollama
        stub.resposta_chat = json.dumps({
            "intencao": "explicar_defeito",
            "parametros": {"defeito_id": "DEF-001", "inventado": "x"},
        })
        client = criar_cliente_ollama(host)

        c = classificar_intencao("me explique o defeito DEF-001", client=client)

        assert c.origem == "llm"
        assert c.parametros == {"defeito_id": "DEF-001"}

    def test_numero_onde_se_espera_texto_e_convertido(self, stub_ollama):
        host, stub = stub_ollama
        stub.resposta_chat = '{"intencao": "explicar_defeito", "parametros": {"defeito_id": 123}}'
        client = criar_cliente_ollama(host)

        c = classificar_intencao("defeito 123", client=client)

        assert c.origem == "llm"
        assert c.parametros == {"defeito_id": "123"}

    def test_desconhecida_do_llm_ainda_tenta_o_regex(self, stub_ollama):
        """O regex conhece formulacoes que o modelo pode nao reconhecer."""
        host, stub = stub_ollama
        stub.resposta_chat = '{"intencao": "desconhecida", "parametros": {}}'
        client = criar_cliente_ollama(host)

        c = classificar_intencao("Quais equipamentos estao sujeitos a NR-12?", client=client)

        assert c.origem == "fallback"
        assert c.intencao == "conformidade_normativa"


class TestErroDeParametroNaExecucao:
    def test_executar_com_param_faltando_levanta_mensagem_legivel(self):
        from api.orquestrador import executar_intencao

        c = ClassificacaoIntencao(intencao="explicar_defeito", parametros={})
        with pytest.raises(ValueError) as exc:
            executar_intencao(c, session=None)
        mensagem = str(exc.value)
        assert "defeito_id" in mensagem
        assert "pydantic" not in mensagem.lower()


class TestPromptDesambigua:
    """O prompt precisa distinguir as tres intencoes que falam de norma."""

    def test_declara_parametros_obrigatorios(self):
        prompt = _construir_prompt_sistema()
        assert "obrigatorios" in prompt

    def test_proibe_null(self):
        prompt = _construir_prompt_sistema()
        assert "Nunca use null" in prompt

    def test_ensina_a_escolher_entre_as_intencoes_de_norma(self):
        prompt = _construir_prompt_sistema()
        assert "conformidade_normativa" in prompt
        assert "norma_id" in prompt
        assert "ISO 14224" in prompt
