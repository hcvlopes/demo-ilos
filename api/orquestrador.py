"""Orquestrador de classificacao de intencao via LLM.

Fluxo:
1. Recebe pergunta em linguagem natural.
2. Envia ao LLM com lista de intencoes disponiveis e seus parametros.
3. LLM retorna nome da intencao + parametros tipados (JSON).
4. Orquestrador resolve a intencao no registry e executa com sessao do grafo.
5. Retorna EnvelopeEvidencia.

O LLM nunca escreve Cypher — apenas classifica intencao e preenche parametros.
"""

from __future__ import annotations

import json
import os

import re

from pydantic import BaseModel

from intents.base import EnvelopeEvidencia
from intents.registry import REGISTRY, get_intencao


class ClassificacaoIntencao(BaseModel):
    """Resultado da classificacao.

    `origem` declara qual classificador produziu o resultado: "llm" quando o
    Ollama respondeu, "fallback" quando o classificador por regex assumiu.
    `motivo_fallback` guarda a causa da degradacao para diagnostico.
    """

    intencao: str
    parametros: dict
    origem: str = "llm"
    motivo_fallback: str | None = None


class ResultadoOrquestrador(BaseModel):
    """Resultado completo do orquestrador."""

    pergunta: str
    intencao_classificada: str
    parametros: dict
    origem_classificacao: str = "llm"
    motivo_fallback: str | None = None
    envelope: EnvelopeEvidencia


def _construir_prompt_sistema() -> str:
    linhas = [
        "Voce e um classificador de intencoes para um sistema de gestao de ativos industriais.",
        "Dada uma pergunta do usuario, identifique a intencao e extraia os parametros.",
        "",
        "Intencoes disponiveis:",
    ]
    for nome, cls in REGISTRY.items():
        inst = cls()
        import inspect
        sig = inspect.signature(cls.executar)
        params = list(sig.parameters.values())
        if len(params) >= 3:
            param_type = params[2].annotation
            campos = list(param_type.model_fields.keys()) if hasattr(param_type, "model_fields") else []
        else:
            campos = []
        linhas.append(f"- {nome}: {inst.descricao}. Parametros: {campos}")

    linhas.extend([
        "",
        "Responda APENAS com JSON valido no formato:",
        '{"intencao": "<nome>", "parametros": {<chave>: <valor>}}',
        "",
        "Se a pergunta nao corresponder a nenhuma intencao, responda:",
        '{"intencao": "desconhecida", "parametros": {}}',
        "",
        "Nao inclua explicacoes, apenas o JSON.",
    ])
    return "\n".join(linhas)


_REGRAS_FALLBACK = [
    (r"expli(?:que|car)\b.*\bprocesso\b", "explicar_processo", "processo_id"),
    (r"expli(?:que|car)\b.*\bdefeito\b", "explicar_defeito", "defeito_id"),
    (r"equipamentos?\b.*\bativo\b|listar?\b.*\bequipamentos?\b", "listar_equipamentos_ativo", "ativo_id"),
    (r"resumo\b.*\bsistema\b|sistema\b.*\bresumo\b", "resumo_sistema", "sistema_id"),
    (r"resumo\b.*\bedifica|edifica.*\bresumo\b", "resumo_edificacao", "edificacao_id"),
    (r"depend[eê]ncia|upstream|downstream", "dependencias_ativo", "ativo_id"),
    (r"defeitos?\s+(aberto|pendente)|aberto.*defeito|quais\s+defeitos|defeitos\s+est[aã]o", "defeitos_abertos", None),
    (r"ord(?:em|ens)\s+(?:de\s+)?manuten[çc][aã]o", "ordens_manutencao", "equipamento_id"),
    (r"norma|regulament|requisito", "normas_aplicaveis", "equipamento_id"),
    (r"monitor|sensor|medi[çc][aã]o|condi[çc][aã]o", "monitoramento_equipamento", "equipamento_id"),
    (r"cadeia\b.*\bfalha|falha.*\bcadeia|modo.*causa.*mecanismo", "cadeia_falha", "defeito_id"),
    (r"estat[ií]stica|lambda|confiabilidade.*classe|classe.*confiabilidade", "estatisticas_classe", "classe_id"),
    (r"impacto.*parada|parada.*impacto|redundância|redund[aâ]ncia", "impacto_parada", "ativo_id"),
    (r"plano.*manuten|manuten.*plano", "plano_manutencao_ativo", "ativo_id"),
    (r"a[çc][oõ]es?\s+permitid|pode\s+fazer|autoriza", "acoes_permitidas", "equipamento_id"),
    (r"hist[oó]rico|eventos?\s+de\s+falha|timeline", "historico_equipamento", "equipamento_id"),
    (r"risco|ranking|escore", "ativos_em_risco_por_processo", "processo_id"),
]

_ID_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]{1,5}){1,3})\b")


def _classificar_fallback(pergunta: str, motivo: str | None = None) -> ClassificacaoIntencao:
    """Classificador por regex — fallback quando o LLM nao esta disponivel."""
    texto = pergunta.lower()
    for pattern, intencao, param_key in _REGRAS_FALLBACK:
        if re.search(pattern, texto):
            parametros = {}
            if param_key:
                match = _ID_PATTERN.search(pergunta)
                if match:
                    parametros[param_key] = match.group(1)
                else:
                    parametros[param_key] = ""
            return ClassificacaoIntencao(
                intencao=intencao,
                parametros=parametros,
                origem="fallback",
                motivo_fallback=motivo,
            )
    return ClassificacaoIntencao(
        intencao="desconhecida",
        parametros={},
        origem="fallback",
        motivo_fallback=motivo,
    )


def criar_cliente_ollama(host: str | None = None):
    """Cria o cliente Ollama. Levanta se o pacote nao estiver instalado."""
    from ollama import Client as OllamaClient

    if host is None:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return OllamaClient(host=host)


def verificar_ollama(client=None, modelo: str | None = None) -> dict:
    """Diagnostica o LLM: servidor alcancavel e modelo baixado.

    Devolve dict com `disponivel`, `host`, `modelo`, `modelos_disponiveis` e
    `detalhe`. Usado pelo /saude para que a degradacao para regex seja
    visivel em vez de silenciosa.
    """
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if modelo is None:
        modelo = os.environ.get("OLLAMA_MODEL", "llama3.1")

    info = {
        "disponivel": False,
        "host": host,
        "modelo": modelo,
        "modelos_disponiveis": [],
        "detalhe": "",
    }

    try:
        if client is None:
            client = criar_cliente_ollama(host)
        resposta = client.list()
    except ImportError:
        info["detalhe"] = "Pacote 'ollama' nao instalado. Rode: pip install -e ."
        return info
    except Exception as e:
        info["detalhe"] = f"Servidor Ollama inacessivel em {host}: {e}"
        return info

    nomes = []
    for m in resposta.get("models", []) if isinstance(resposta, dict) else getattr(resposta, "models", []):
        nome = m.get("model") or m.get("name") if isinstance(m, dict) else getattr(m, "model", None)
        if nome:
            nomes.append(nome)
    info["modelos_disponiveis"] = nomes

    # Ollama aceita "llama3.1" para uma tag "llama3.1:latest".
    if any(n == modelo or n.split(":")[0] == modelo.split(":")[0] for n in nomes):
        info["disponivel"] = True
        info["detalhe"] = f"Ollama respondendo em {host} com o modelo '{modelo}'."
    else:
        info["detalhe"] = (
            f"Ollama respondendo em {host}, mas o modelo '{modelo}' nao foi baixado. "
            f"Rode: ollama pull {modelo}"
        )
    return info


def classificar_intencao(
    pergunta: str,
    client=None,
    modelo: str | None = None,
) -> ClassificacaoIntencao:
    """Classifica a intencao via LLM (Ollama), degradando para regex se falhar.

    A degradacao nunca e silenciosa: o resultado carrega `origem` e
    `motivo_fallback` para que a interface mostre qual classificador rodou.
    """
    if modelo is None:
        modelo = os.environ.get("OLLAMA_MODEL", "llama3.1")

    try:
        if client is None:
            client = criar_cliente_ollama()

        response = client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _construir_prompt_sistema()},
                {"role": "user", "content": pergunta},
            ],
            format="json",
        )

        texto = response["message"]["content"].strip()

        if texto.startswith("```"):
            linhas = texto.split("\n")
            texto = "\n".join(linhas[1:-1])

        dados = json.loads(texto)
    except ImportError:
        return _classificar_fallback(pergunta, "Pacote 'ollama' nao instalado.")
    except json.JSONDecodeError as e:
        return _classificar_fallback(pergunta, f"LLM devolveu JSON invalido: {e}")
    except Exception as e:
        return _classificar_fallback(pergunta, f"Falha ao consultar o LLM: {e}")

    intencao = dados.get("intencao", "desconhecida")
    if intencao not in REGISTRY and intencao != "desconhecida":
        return _classificar_fallback(
            pergunta, f"LLM classificou intencao inexistente: '{intencao}'.",
        )

    return ClassificacaoIntencao(
        intencao=intencao,
        parametros=dados.get("parametros", {}) or {},
        origem="llm",
    )


def executar_intencao(
    classificacao: ClassificacaoIntencao,
    session,
) -> EnvelopeEvidencia:
    """Resolve e executa a intencao classificada."""
    inst = get_intencao(classificacao.intencao)

    import inspect
    sig = inspect.signature(type(inst).executar)
    params_list = list(sig.parameters.values())
    param_type = params_list[2].annotation

    params_tipados = param_type(**classificacao.parametros)
    return inst.executar(session, params_tipados)


def orquestrar(
    pergunta: str,
    session,
    client=None,
    modelo: str | None = None,
) -> ResultadoOrquestrador:
    """Pipeline completo: pergunta -> classificacao -> execucao -> envelope."""
    classificacao = classificar_intencao(pergunta, client=client, modelo=modelo)
    envelope = executar_intencao(classificacao, session)
    return ResultadoOrquestrador(
        pergunta=pergunta,
        intencao_classificada=classificacao.intencao,
        parametros=classificacao.parametros,
        origem_classificacao=classificacao.origem,
        motivo_fallback=classificacao.motivo_fallback,
        envelope=envelope,
    )
