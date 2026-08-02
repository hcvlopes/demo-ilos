"""Testes da API e orquestrador (F6).

Testes offline — validam estrutura, classificacao mockada e contratos.
Nenhuma chamada real ao LLM ou FalkorDB.
"""

import inspect
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api.main import IntencaoInfo, PerguntaRequest, SaudeResponse, app
from api.orquestrador import (
    ClassificacaoIntencao,
    ResultadoOrquestrador,
    _construir_prompt_sistema,
    executar_intencao,
)
from intents.base import EnvelopeEvidencia, IntencaoBase
from intents.registry import REGISTRY


class TestClassificacaoIntencao:
    """Validacao do modelo de classificacao."""

    def test_cria_classificacao(self):
        c = ClassificacaoIntencao(intencao="explicar_defeito", parametros={"defeito_id": "DEF-001"})
        assert c.intencao == "explicar_defeito"
        assert c.parametros["defeito_id"] == "DEF-001"

    def test_classificacao_desconhecida(self):
        c = ClassificacaoIntencao(intencao="desconhecida", parametros={})
        assert c.intencao == "desconhecida"


class TestPromptSistema:
    """O prompt do sistema lista todas as intencoes do registry."""

    def test_prompt_contem_todas_intencoes(self):
        prompt = _construir_prompt_sistema()
        for nome in REGISTRY:
            assert nome in prompt, f"Intencao '{nome}' nao encontrada no prompt"

    def test_prompt_contem_formato_json(self):
        prompt = _construir_prompt_sistema()
        assert '"intencao"' in prompt
        assert '"parametros"' in prompt

    def test_prompt_nao_aceita_query(self):
        prompt = _construir_prompt_sistema()
        assert "cypher" not in prompt.lower() or "query" not in prompt.lower()


class TestExecutarIntencao:
    """Execucao de intencao com sessao mockada."""

    def _mock_session(self, result_single=None, result_iter=None):
        session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = result_single
        if result_iter is not None:
            mock_result.__iter__ = MagicMock(return_value=iter(result_iter))
        else:
            mock_result.__iter__ = MagicMock(return_value=iter([]))
        session.run.return_value = mock_result
        return session

    def test_executa_intencao_valida(self):
        classificacao = ClassificacaoIntencao(
            intencao="explicar_defeito",
            parametros={"defeito_id": "DEF-001"},
        )
        session = self._mock_session(result_single=None)
        envelope = executar_intencao(classificacao, session)
        assert isinstance(envelope, EnvelopeEvidencia)
        assert envelope.afirmacao

    def test_executa_intencao_historico(self):
        classificacao = ClassificacaoIntencao(
            intencao="historico_equipamento",
            parametros={"equipamento_id": "EQ-TRE-001"},
        )
        session = self._mock_session(result_single=None)
        envelope = executar_intencao(classificacao, session)
        assert isinstance(envelope, EnvelopeEvidencia)

    def test_intencao_invalida_levanta_keyerror(self):
        classificacao = ClassificacaoIntencao(
            intencao="nao_existe",
            parametros={},
        )
        session = self._mock_session()
        with pytest.raises(KeyError):
            executar_intencao(classificacao, session)

    def test_retorno_e_envelope(self):
        classificacao = ClassificacaoIntencao(
            intencao="acoes_permitidas",
            parametros={"defeito_id": "DEF-001"},
        )
        session = self._mock_session(result_single=None)
        envelope = executar_intencao(classificacao, session)
        campos = set(EnvelopeEvidencia.model_fields.keys())
        assert set(type(envelope).model_fields.keys()) == campos


class TestResultadoOrquestrador:
    """Validacao do modelo de resultado."""

    def test_resultado_completo(self):
        env = EnvelopeEvidencia(
            afirmacao="teste",
            nos=[],
            arestas=[],
            calculos=[],
            normas=[],
            lacunas=[],
        )
        r = ResultadoOrquestrador(
            pergunta="O que ha de errado com DEF-001?",
            intencao_classificada="explicar_defeito",
            parametros={"defeito_id": "DEF-001"},
            envelope=env,
        )
        assert r.pergunta
        assert r.intencao_classificada == "explicar_defeito"


class TestPerguntaRequest:
    """Validacao do request de pergunta."""

    def test_pergunta_valida(self):
        p = PerguntaRequest(pergunta="Qual o historico do EQ-TRE-001?")
        assert p.pergunta

    def test_pergunta_vazia_rejeitada(self):
        with pytest.raises(Exception):
            PerguntaRequest(pergunta="")

    def test_pergunta_longa_rejeitada(self):
        with pytest.raises(Exception):
            PerguntaRequest(pergunta="x" * 2001)


class TestEndpointIntencoes:
    """GET /intencoes retorna lista de intencoes."""

    def test_lista_intencoes(self):
        client = TestClient(app)
        resp = client.get("/intencoes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 4
        nomes = {d["nome"] for d in data}
        assert "explicar_defeito" in nomes
        assert "ativos_em_risco_por_processo" in nomes

    def test_cada_intencao_tem_campos(self):
        client = TestClient(app)
        resp = client.get("/intencoes")
        for item in resp.json():
            assert "nome" in item
            assert "descricao" in item
            assert "parametros" in item
            assert isinstance(item["parametros"], list)


class TestEndpointSaude:
    """GET /saude retorna status."""

    def test_saude_sem_falkordb(self):
        client = TestClient(app)
        resp = client.get("/saude")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["intencoes"] >= 4


class TestSegurancaAPI:
    """Nenhuma rota aceita query/cypher como entrada."""

    def test_pergunta_request_nao_tem_campo_query(self):
        campos = set(PerguntaRequest.model_fields.keys())
        proibidos = {"query", "cypher", "consulta", "cypher_query", "raw_query"}
        assert not campos & proibidos

    def test_nenhum_endpoint_aceita_query(self):
        for route in app.routes:
            if hasattr(route, "dependant"):
                for param in route.dependant.body_params:
                    assert param.name not in {"query", "cypher", "consulta"}
