"""Testes da UI (F7).

Valida que o HTML existe, e servido corretamente pela API,
contem os elementos essenciais e nao usa recursos externos.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import WEB_DIR, app


client = TestClient(app)


class TestArquivoHTML:
    """O arquivo index.html existe e tem conteudo."""

    def test_arquivo_existe(self):
        assert (WEB_DIR / "index.html").exists()

    def test_arquivo_nao_vazio(self):
        content = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        assert len(content) > 500


class TestServeUI:
    """GET / retorna o HTML da UI."""

    def test_root_retorna_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_root_contem_titulo(self):
        resp = client.get("/")
        assert "Demo ILOS" in resp.text


class TestConteudoHTML:
    """O HTML contem os elementos essenciais do demo."""

    def _html(self) -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    def test_tem_input_pergunta(self):
        assert 'id="input-pergunta"' in self._html()

    def test_tem_botao_enviar(self):
        assert 'id="btn-enviar"' in self._html()

    def test_tem_painel_evidencia(self):
        assert 'id="evidence-panel"' in self._html()

    def test_chama_endpoint_pergunta(self):
        assert "'/pergunta'" in self._html() or '"/pergunta"' in self._html()

    def test_chama_endpoint_intencoes(self):
        assert "'/intencoes'" in self._html() or '"/intencoes"' in self._html()

    def test_renderiza_envelope(self):
        html = self._html()
        assert "afirmacao" in html
        assert "calculos" in html
        assert "lacunas" in html
        assert "normas" in html


class TestSemRecursosExternos:
    """O HTML nao referencia CDNs ou recursos externos."""

    def _html(self) -> str:
        return (WEB_DIR / "index.html").read_text(encoding="utf-8")

    def test_sem_cdn(self):
        html = self._html()
        assert "cdn." not in html.lower()
        assert "unpkg.com" not in html.lower()
        assert "jsdelivr" not in html.lower()

    def test_sem_script_externo(self):
        html = self._html()
        scripts = re.findall(r'<script\s+src=["\']([^"\']+)', html)
        for src in scripts:
            assert not src.startswith("http"), f"Script externo encontrado: {src}"

    def test_sem_link_css_externo(self):
        html = self._html()
        links = re.findall(r'<link[^>]+href=["\']([^"\']+)', html)
        for href in links:
            assert not href.startswith("http"), f"CSS externo encontrado: {href}"


class TestAPIEndpointsParaUI:
    """Os endpoints necessarios para a UI existem e respondem."""

    def test_get_intencoes_retorna_lista(self):
        resp = client.get("/intencoes")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 4

    def test_get_saude_retorna_json(self):
        resp = client.get("/saude")
        assert resp.status_code == 200
        data = resp.json()
        assert "intencoes" in data
