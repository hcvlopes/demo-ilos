"""Narracao do envelope de evidencia em linguagem natural.

O envelope e completo mas seco: "A norma NR-12 impoe 4 requisito(s) (3 de
criticidade alta) e alcanca 26 de 49 equipamento(s) do parque". Correto, e
dificil de ouvir. Este modulo pede ao LLM que transforme o envelope em
prosa.

O ponto que faz isso ser seguro: o narrador **nao tem acesso ao grafo**. Ele
recebe apenas o envelope ja montado e reescreve. Nao pode inventar numero
que nao esteja ali, porque nao tem de onde tirar — e se inventar, o painel
de evidencia ao lado mostra os numeros de verdade. A narracao e camada de
apresentacao; a evidencia continua sendo a fonte.

Sem LLM disponivel, devolve a afirmacao original. Nunca falha a resposta
por causa da narracao.
"""

from __future__ import annotations

import json

from intents.base import EnvelopeEvidencia

_PROMPT_NARRADOR = """Voce explica resultados de analise de ativos industriais \
para um engenheiro de manutencao.

Receba os dados apurados e escreva a resposta em portugues do Brasil.

Regras:
- Use SOMENTE os numeros e fatos fornecidos. Nao invente nada, nao arredonde \
metrica de confiabilidade, nao acrescente recomendacao que os dados nao sustentem.
- 2 a 4 frases. Comece pela resposta, nao por preambulo.
- Escreva como quem explica a um colega: sem "(s)" de plural, sem repetir \
identificadores desnecessariamente, sem jargao de banco de dados.
- Se houver lacunas, mencione a mais importante em uma frase, como ressalva \
honesta — nao como desculpa.
- Se houver norma citada, diga o codigo dela.
- Nao use marcacao, listas nem titulos. Apenas paragrafo corrido.
"""


def _resumir_envelope(envelope: EnvelopeEvidencia, pergunta: str) -> str:
    """Monta o material que o narrador recebe.

    Os nos entram so como contagem por rotulo: mandar 94 nos inteiros gastaria
    o contexto sem melhorar a frase, e aumentaria a chance de o modelo comecar
    a listar identificadores.
    """
    por_rotulo: dict[str, int] = {}
    for no in envelope.nos:
        por_rotulo[no.label] = por_rotulo.get(no.label, 0) + 1

    dados = {
        "pergunta": pergunta,
        "resposta_apurada": envelope.afirmacao,
        "entidades_encontradas": por_rotulo,
        "calculos": [
            {
                "nome": c.nome,
                "valor": c.valor,
                "unidade": c.unidade,
                **(
                    {"intervalo_confianca_95": [c.ic_inferior, c.ic_superior]}
                    if c.ic_inferior is not None
                    else {}
                ),
            }
            for c in envelope.calculos
        ],
        "normas": [{"codigo": n.codigo, "sobre": n.descricao} for n in envelope.normas],
        "lacunas": envelope.lacunas,
    }
    return json.dumps(dados, ensure_ascii=False, indent=2)


def narrar(
    envelope: EnvelopeEvidencia,
    pergunta: str,
    client=None,
    modelo: str | None = None,
) -> tuple[str, bool]:
    """Devolve (texto, veio_do_llm).

    Em qualquer falha devolve a afirmacao original com veio_do_llm=False. A
    narracao e enfeite: nunca pode derrubar uma resposta que o grafo ja deu.
    """
    import os

    if modelo is None:
        modelo = os.environ.get("OLLAMA_MODEL", "llama3.1")

    try:
        if client is None:
            from api.orquestrador import criar_cliente_ollama

            client = criar_cliente_ollama()

        resposta = client.chat(
            model=modelo,
            messages=[
                {"role": "system", "content": _PROMPT_NARRADOR},
                {"role": "user", "content": _resumir_envelope(envelope, pergunta)},
            ],
        )
        texto = resposta["message"]["content"].strip()
    except Exception:  # noqa: BLE001 — narracao nunca derruba a resposta
        return envelope.afirmacao, False

    if not texto:
        return envelope.afirmacao, False

    # Modelo pequeno as vezes devolve o JSON de volta, ou abre com uma
    # introducao inutil. Nos dois casos a afirmacao original e melhor.
    if texto.lstrip().startswith(("{", "[")):
        return envelope.afirmacao, False

    return texto, True
