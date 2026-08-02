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


# Extratores de parametro. Cada um sabe reconhecer um tipo de referencia na
# pergunta; o padrao generico cobre IDs compostos como ATV-PRT-01.
_ID_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]{1,5}){1,3})\b")

# Codigo de norma nao segue o formato de ID: "NBR 5410" e "ISO 14224" tem
# espaco, e o usuario escreve como quiser.
_NORMA_PATTERN = re.compile(
    r"\b(NR\s*-?\s*\d{1,2}|NBR\s*\d{3,5}|ISO\s*\d{4,5}|NORMA-[A-Z0-9]+)\b",
    re.IGNORECASE,
)

# Papel vem por nome, nao por codigo — ninguem pergunta por "PAPEL-TEC".
_PAPEIS = [
    (r"t[eé]cnic", "PAPEL-TEC"),
    (r"supervisor", "PAPEL-SUP"),
    (r"engenheir", "PAPEL-ENG"),
]


def _extrair_id(pergunta: str) -> str:
    m = _ID_PATTERN.search(pergunta)
    return m.group(1) if m else ""


def _extrair_norma(pergunta: str) -> str:
    """Normaliza o codigo da norma para a forma gravada no grafo."""
    m = _NORMA_PATTERN.search(pergunta)
    if not m:
        return ""
    bruto = m.group(1).upper()
    if bruto.startswith("NORMA-"):
        return bruto
    digitos = re.sub(r"\D", "", bruto)
    if bruto.startswith("NBR"):
        return f"NBR {digitos}"
    if bruto.startswith("ISO"):
        return f"ISO {digitos}:2016"
    if bruto.startswith("NR"):
        return f"NR-{digitos}"
    return bruto


def _extrair_papel(pergunta: str) -> str:
    texto = pergunta.lower()
    for padrao, papel_id in _PAPEIS:
        if re.search(padrao, texto):
            return papel_id
    return _extrair_id(pergunta)


# Ordem importa: a primeira regra que casar decide. As mais especificas vem
# antes das genericas — "quais equipamentos estao sujeitos a NR-12" precisa
# cair em conformidade_normativa, nao na regra generica de "norma".
_REGRAS_FALLBACK = [
    # --- Conformidade: tres regras disputam o vocabulario de norma ---
    (
        (
            r"(?:sujeit|alcanc|abrang|conformidade|atende).*"
            r"(?:nr\s*-?\s*\d|nbr\s*\d|iso\s*\d)"
            r"|(?:nr\s*-?\s*\d|nbr\s*\d|iso\s*\d).*"
            r"(?:sujeit|alcanc|abrang|exige|imp[oõ]e|requisito|aplica|equipamento)"
        ),
        "conformidade_normativa", "norma_id", _extrair_norma),
    (r"requisito", "requisitos_equipamento", "equipamento_id", _extrair_id),
    (r"\bnormas?\b|regulament", "normas_aplicaveis", "equipamento_id", _extrair_id),

    # --- Autorizacao ---
    (
        (
            r"(?:t[eé]cnic|supervisor|engenheir).*(?:pode|autoriz|permitid|executar)"
            r"|(?:pode|autoriz|permitid).*(?:t[eé]cnic|supervisor|engenheir)"
            r"|\bpap[eé]is\b|\bpapel\b|quem\s+(?:pode|autoriza)"
        ),
        "acoes_por_papel", "papel_id", _extrair_papel),
    (
        (
            r"a[çc][oõ]es?\s+permitid|o\s+que\s+(?:eu\s+)?posso\s+fazer|pode\s+ser\s+feito"
            r"|que\s+a[çc][aã]o|quais\s+a[çc][oõ]es"
        ),
        "acoes_permitidas", "defeito_id", _extrair_id),

    # --- Defeitos: resolvido antes de aberto ---
    (
        (
            r"defeitos?\b.{0,24}?(?:resolvid|encerrad|fechad|conclu)"
            r"|(?:resolvid|encerrad|fechad).*defeito|hist[oó]rico\s+de\s+resolu"
        ),
        "defeitos_resolvidos", None, None),
    (
        (
            r"defeitos?\s+(?:em\s+)?(?:aberto|abertos|pendente)|aberto.*defeito"
            r"|quais\s+defeitos|defeitos?\s+est[aã]o|\blist\w*\s+(?:os\s+)?defeitos|tem\s+defeito"
        ),
        "defeitos_abertos", None, None),

    # --- Cadeia e localizacao ---
    (r"cadeia\b.*\bfalha|falha.*\bcadeia|modo.*causa.*mecanismo",
     "cadeia_falha", "defeito_id", _extrair_id),
    (
        (
            r"(?:qual|que)\s+(?:a\s+)?(?:parte|pe[çc]a|componente)|onde\s+(?:esta|est[aá]|fica)"
            r"|localiza|parte\s+afetada|mesma\s+pe[çc]a"
        ),
        "localizacao_defeito", "defeito_id", _extrair_id),

    # --- Ordens e planos ---
    (r"etapas?\b|passos?\b|sequ[eê]ncia\s+de\s+execu|quem\s+executa",
     "etapas_ordem", "ordem_id", _extrair_id),
    (r"plano.*manuten|manuten.*plano|preventiv.*cobr|lista\s+de\s+tarefa",
     "plano_manutencao_ativo", "ativo_id", _extrair_id),
    (r"ord(?:em|ens)\s+(?:de\s+)?manuten|\bordens?\b",
     "ordens_manutencao", "equipamento_id", _extrair_id),

    # --- Notas ---
    (
        (
            r"consequ[eê]ncia|gravidade\s+das?\s+nota|severidade|impacto\s+das?\s+nota"
            r"|notas?\s+de\s+manuten"
        ),
        "consequencia_notas", "equipamento_id", _extrair_id),

    # --- Organizacao ---
    (
        (
            r"centro\s+de\s+(?:trabalho|manuten)|carga\s+d[eo]\s+centro"
            r"|quantos?\s+equipamentos?\s+atend"
        ),
        "carga_centro_trabalho", "centro_id", _extrair_id),
    (
        (
            r"grupo\s+de\s+planejamento|planejamento\s+central|escopo\s+do\s+grupo"
            r"|planejad[oa]\s+por"
        ),
        "escopo_grupo_planejamento", "grupo_id", _extrair_id),

    # --- Comparacao e risco ---
    (
        (
            r"(?:ranking|compar|pior|melhor|menos\s+confi[aá]vel|mais\s+cr[ií]tic)"
            r".*\bsistemas?\b|\bsistemas?\b.*"
            r"(?:ranking|compar|pior|menos\s+confi[aá]vel|mais\s+cr[ií]tic)"
        ),
        "ranking_sistemas", "edificacao_id", _extrair_id),
    (r"risco|escore|ranking", "ativos_em_risco_por_processo", "processo_id", _extrair_id),

    # --- Navegacao e explicacao ---
    (r"expli(?:que|car)\b.*\bprocesso\b|processo\s+operacional|indicador",
     "explicar_processo", "processo_id", _extrair_id),
    (
        (
            r"expli(?:que|car)\b.*\bdefeito\b|o\s+que\s+(?:e|h[aá])\s+(?:no\s+)?defeito"
            r"|detalh.*defeito|sobre\s+o\s+defeito"
        ),
        "explicar_defeito", "defeito_id", _extrair_id),
    (r"equipamentos?\b.*\bativo\b|\blist\w*\b.*\bequipamentos?\b|comp[oõ]e\s+o\s+ativo",
     "listar_equipamentos_ativo", "ativo_id", _extrair_id),
    (r"resumo\b.*\bsistema\b|sistema\b.*\bresumo\b|vis[aã]o\s+geral.*sistema",
     "resumo_sistema", "sistema_id", _extrair_id),
    (
        (
            r"resumo\b.*\bedifica|edifica.*\bresumo\b|vis[aã]o\s+geral.*edifica"
            r"|planta\s+inteira"
        ),
        "resumo_edificacao", "edificacao_id", _extrair_id),
    (r"depend[eê]ncia|upstream|downstream|do\s+que\s+depende|alimenta",
     "dependencias_ativo", "ativo_id", _extrair_id),
    (
        (
            r"impacto.*parada|parada.*impacto|redund[aâ]ncia|se\s+.*\bparar\b"
            r"|deixar\s+de\s+operar"
        ),
        "impacto_parada", "ativo_id", _extrair_id),
    (r"monitor|sensor|medi[çc][aã]o|condi[çc][aã]o|tend[eê]ncia",
     "monitoramento_equipamento", "equipamento_id", _extrair_id),
    (
        (
            r"estat[ií]stica|lambda|taxa\s+de\s+falha|confiabilidade.*classe"
            r"|classe.*confiabilidade"
        ),
        "estatisticas_classe", "classe_id", _extrair_id),
    (r"hist[oó]rico|eventos?\s+de\s+falha|timeline|j[aá]\s+falhou",
     "historico_equipamento", "equipamento_id", _extrair_id),
]


def _classificar_fallback(pergunta: str, motivo: str | None = None) -> ClassificacaoIntencao:
    """Classificador por regex — fallback quando o LLM nao esta disponivel."""
    texto = pergunta.lower()
    for pattern, intencao, param_key, extrator in _REGRAS_FALLBACK:
        if re.search(pattern, texto):
            parametros = {}
            if param_key:
                # Extrator ausente equivale ao generico de ID.
                parametros[param_key] = (extrator or _extrair_id)(pergunta)
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
