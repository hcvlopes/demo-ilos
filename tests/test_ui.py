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


class TestCatalogoDeExemplos:
    """O catalogo da UI e a porta de entrada da demo.

    Duas garantias: nenhum exemplo mostrado pode falhar na classificacao, e
    nenhuma intencao pode ficar sem exemplo. A segunda e a que importa no
    longo prazo — intencao nova sem exemplo e intencao que ninguem descobre
    que existe.
    """

    @staticmethod
    def _perguntas() -> list[str]:
        html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(
            encoding="utf-8",
        )
        inicio = html.index("const GRUPOS_EXEMPLO")
        bloco = html[inicio:html.index("\n];\n", inicio)]
        return re.findall(r"^      '(.+?)',$", bloco, re.M)

    def test_catalogo_nao_esta_vazio(self):
        assert len(self._perguntas()) >= 30

    def test_nenhum_exemplo_cai_em_desconhecida(self):
        """Exemplo mostrado na tela nao pode devolver 422 ao ser clicado."""
        from api.orquestrador import _classificar_fallback

        falhas = [
            p for p in self._perguntas()
            if _classificar_fallback(p).intencao == "desconhecida"
        ]
        assert not falhas, f"Exemplos que o classificador nao reconhece: {falhas}"

    def test_toda_intencao_tem_exemplo(self):
        from api.orquestrador import _classificar_fallback
        from intents.registry import REGISTRY

        alcancadas = {_classificar_fallback(p).intencao for p in self._perguntas()}
        faltando = sorted(set(REGISTRY) - alcancadas)
        assert not faltando, (
            f"Intencoes sem exemplo no catalogo da UI: {faltando}"
        )

    def test_parametros_dos_exemplos_sao_tipaveis(self):
        """Clicar num exemplo nao pode gerar ValidationError."""
        import inspect

        from api.orquestrador import _classificar_fallback
        from intents.registry import get_intencao

        for pergunta in self._perguntas():
            c = _classificar_fallback(pergunta)
            inst = get_intencao(c.intencao)
            sig = inspect.signature(type(inst).executar)
            tipo = list(sig.parameters.values())[2].annotation
            tipo(**c.parametros)


class TestNarrativaNaInterface:
    """A narrativa nao pode substituir o numero apurado — precisa acompanha-lo."""

    @staticmethod
    def _html() -> str:
        return (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(
            encoding="utf-8",
        )

    def test_usa_a_narrativa_quando_existe(self):
        assert "data.narrativa || data.envelope.afirmacao" in self._html()

    def test_mostra_o_apurado_junto_da_narrativa(self):
        """Se o modelo arredondar, o valor do grafo esta na linha seguinte."""
        html = self._html()
        assert "msg-apurado" in html
        assert "data.envelope.afirmacao" in html

    def test_nao_duplica_quando_nao_houve_narracao(self):
        """Sem LLM narrativa == afirmacao; mostrar as duas seria ruido."""
        html = self._html()
        assert "data.narrativa !== data.envelope.afirmacao" in html

    def test_marca_o_caminho_da_resposta(self):
        html = self._html()
        assert "caminho-livre" in html
        assert "caminho-intencao" in html
        assert "consulta gerada" in html

    def test_exibe_o_cypher_gerado(self):
        html = self._html()
        assert "cypher_gerado" in html
        assert "cypher-bloco" in html
