"""Testes do narrador.

A narracao e camada de apresentacao: pode melhorar a resposta, nunca pode
derruba-la nem inventar numero. Os testes cobrem as duas garantias.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest

from api.narrador import _resumir_envelope, narrar
from api.orquestrador import criar_cliente_ollama
from intents.base import CalculoEvidencia, EnvelopeEvidencia, NoEvidencia, NormaEvidencia


def _envelope():
    return EnvelopeEvidencia(
        afirmacao="A norma NR-12 impoe 4 requisito(s) e alcanca 26 de 49 equipamento(s).",
        nos=[
            NoEvidencia(label="Norma", id="NORMA-NR12"),
            NoEvidencia(label="Equipamento", id="EQ-1"),
            NoEvidencia(label="Equipamento", id="EQ-2"),
        ],
        arestas=[],
        calculos=[
            CalculoEvidencia(nome="requisitos", formula="count", valor=4, unidade="requisitos"),
            CalculoEvidencia(
                nome="lambda_hat", formula="n/h", valor=0.001,
                unidade="falhas/h_op", ic_inferior=0.0007, ic_superior=0.0014,
            ),
        ],
        normas=[NormaEvidencia(codigo="NR-12", descricao="Seguranca em maquinas")],
        lacunas=["Cobertura parcial."],
    )


class _Stub(BaseHTTPRequestHandler):
    resposta: ClassVar[str] = "A NR-12 exige quatro requisitos e alcanca 26 dos 49 equipamentos."

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        corpo = json.dumps({
            "model": "llama3.1", "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": type(self).resposta},
            "done": True,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


@pytest.fixture
def stub():
    _Stub.resposta = "A NR-12 exige quatro requisitos e alcanca 26 dos 49 equipamentos."
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}", _Stub
    finally:
        srv.shutdown()
        srv.server_close()


class TestNarracao:
    def test_usa_o_texto_do_llm(self, stub):
        host, _ = stub
        texto, do_llm = narrar(_envelope(), "o que a NR-12 exige?", criar_cliente_ollama(host))
        assert do_llm is True
        assert "NR-12" in texto

    def test_sem_llm_devolve_a_afirmacao(self):
        env = _envelope()
        texto, do_llm = narrar(env, "pergunta", criar_cliente_ollama("http://127.0.0.1:1"))
        assert do_llm is False
        assert texto == env.afirmacao

    def test_resposta_vazia_devolve_a_afirmacao(self, stub):
        host, s = stub
        s.resposta = "   "
        env = _envelope()
        texto, do_llm = narrar(env, "pergunta", criar_cliente_ollama(host))
        assert do_llm is False
        assert texto == env.afirmacao

    def test_json_devolvido_por_engano_e_descartado(self, stub):
        """Modelo pequeno as vezes ecoa o JSON de entrada."""
        host, s = stub
        s.resposta = '{"resposta_apurada": "..."}'
        env = _envelope()
        texto, do_llm = narrar(env, "pergunta", criar_cliente_ollama(host))
        assert do_llm is False
        assert texto == env.afirmacao


class TestMaterialEnviadoAoNarrador:
    """O narrador nao recebe o grafo — so o envelope. Nao tem o que inventar."""

    def test_inclui_calculos_com_intervalo(self):
        material = json.loads(_resumir_envelope(_envelope(), "p"))
        lam = next(c for c in material["calculos"] if c["nome"] == "lambda_hat")
        assert lam["intervalo_confianca_95"] == [0.0007, 0.0014]

    def test_nos_entram_como_contagem_e_nao_lista(self):
        """Mandar 94 nos inteiros gastaria contexto e convidaria a listar IDs."""
        material = json.loads(_resumir_envelope(_envelope(), "p"))
        assert material["entidades_encontradas"] == {"Norma": 1, "Equipamento": 2}

    def test_lacunas_chegam_ao_narrador(self):
        material = json.loads(_resumir_envelope(_envelope(), "p"))
        assert material["lacunas"] == ["Cobertura parcial."]

    def test_nao_recebe_sessao_nem_acesso_ao_grafo(self):
        import inspect

        assinatura = inspect.signature(narrar)
        assert "session" not in assinatura.parameters
