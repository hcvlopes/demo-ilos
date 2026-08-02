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

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.orquestrador import (
    ResultadoOrquestrador,
    classificar_intencao,
    executar_intencao,
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


class SaudeResponse(BaseModel):
    status: str
    grafo: str
    intencoes: int


_driver = None
_anthropic_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _driver, _anthropic_client

    try:
        _driver = create_driver()
    except Exception:
        _driver = None

    _anthropic_client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
    )

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
    modelo = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    try:
        classificacao = classificar_intencao(
            req.pergunta, client=_anthropic_client, modelo=modelo,
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na execucao: {e}")

    return ResultadoOrquestrador(
        pergunta=req.pergunta,
        intencao_classificada=classificacao.intencao,
        parametros=classificacao.parametros,
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

    return SaudeResponse(
        status="ok",
        grafo=grafo_status,
        intencoes=len(REGISTRY),
    )
