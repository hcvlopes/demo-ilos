"""FastAPI app — API do demo ILOS.

Endpoints:
- POST /pergunta — recebe pergunta em linguagem natural, retorna envelope de evidencia
- GET  /intencoes — lista intencoes disponiveis com seus parametros
- GET  /saude — health check
- GET  / — UI do demo (web/index.html)
"""

from __future__ import annotations

import inspect
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.orquestrador import (
    ResultadoOrquestrador,
    classificar_intencao,
    criar_cliente_ollama,
    executar_intencao,
    verificar_ollama,
)
from db.adapter import create_driver
from intents.base import EnvelopeEvidencia
from intents.registry import REGISTRY

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class PerguntaRequest(BaseModel):
    pergunta: str = Field(..., min_length=1, max_length=2000)


class IntencaoInfo(BaseModel):
    nome: str
    descricao: str
    parametros: list[str]


class LLMStatus(BaseModel):
    disponivel: bool
    host: str
    modelo: str
    modelos_disponiveis: list[str] = []
    detalhe: str = ""


class SaudeResponse(BaseModel):
    status: str
    grafo: str
    intencoes: int
    llm: LLMStatus
    classificador: str


_driver = None
_llm_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _driver, _llm_client

    try:
        _driver = create_driver()
    except Exception:
        _driver = None

    try:
        _llm_client = criar_cliente_ollama()
    except Exception:
        _llm_client = None

    yield

    if _driver is not None:
        _driver.close()


app = FastAPI(
    title="Demo ILOS — Agentes sobre Grafo de Ativos",
    description="API de intencoes tipadas com envelope de evidencia",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def index():
    """Serve a UI do demo."""
    return FileResponse(WEB_DIR / "index.html")


@app.post("/pergunta", response_model=ResultadoOrquestrador)
def pergunta(req: PerguntaRequest):
    """Recebe pergunta em linguagem natural e retorna envelope de evidencia."""
    modelo = os.environ.get("OLLAMA_MODEL", "llama3.1")

    try:
        classificacao = classificar_intencao(
            req.pergunta, client=_llm_client, modelo=modelo,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro na classificacao: {e}")

    if classificacao.intencao == "desconhecida":
        raise HTTPException(
            status_code=422,
            detail="Intencao nao reconhecida. Reformule a pergunta.",
        )

    if classificacao.intencao not in REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Intencao '{classificacao.intencao}' nao registrada.",
        )

    try:
        with _driver.session() as session:
            envelope = executar_intencao(classificacao, session)
    except KeyError as e:
        # KeyError chega com aspas do repr; a mensagem ja e escrita para o
        # usuario final e nao precisa delas.
        raise HTTPException(status_code=404, detail=str(e).strip('"'))
    except ValueError as e:
        # Parametro faltando ou invalido: e a pergunta que esta incompleta,
        # nao o servidor que quebrou.
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na execucao: {e}")

    return ResultadoOrquestrador(
        pergunta=req.pergunta,
        intencao_classificada=classificacao.intencao,
        parametros=classificacao.parametros,
        origem_classificacao=classificacao.origem,
        motivo_fallback=classificacao.motivo_fallback,
        envelope=envelope,
    )


@app.get("/intencoes", response_model=list[IntencaoInfo])
def listar_intencoes():
    """Lista intencoes disponiveis com seus parametros."""
    resultado = []
    for nome, cls in REGISTRY.items():
        inst = cls()
        sig = inspect.signature(cls.executar)
        params_list = list(sig.parameters.values())
        campos = []
        if len(params_list) >= 3:
            param_type = params_list[2].annotation
            if hasattr(param_type, "model_fields"):
                campos = list(param_type.model_fields.keys())
        resultado.append(IntencaoInfo(nome=nome, descricao=inst.descricao, parametros=campos))
    return resultado


@app.get("/saude", response_model=SaudeResponse)
def saude():
    """Health check — verifica FalkorDB e lista intencoes."""
    grafo_status = "desconectado"
    if _driver is not None:
        try:
            with _driver.session() as session:
                session.run("RETURN 1").single()
            grafo_status = "conectado"
        except Exception:
            grafo_status = "erro"

    llm_info = verificar_ollama(client=_llm_client)

    return SaudeResponse(
        status="ok",
        grafo=grafo_status,
        intencoes=len(REGISTRY),
        llm=LLMStatus(**llm_info),
        classificador="llm" if llm_info["disponivel"] else "fallback-regex",
    )
