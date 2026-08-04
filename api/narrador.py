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

Escreva de forma DECLARATIVA: afirme o que o grafo declara, e diga por que \
aquilo e verdade. Nao relate contagens como se fossem a resposta.

Ruim:  "O processo tem 4 estagios e 2 funcoes de suporte."
Bom:   "O processamento vai do recebimento a expedicao em quatro estagios, e \
depende de energia como funcao essencial de suporte — sem ela o fluxo para \
inteiro, mesmo com todos os estagios sadios."

Regras:
- Use SOMENTE os numeros e fatos fornecidos. Nao invente nada, nao arredonde \
metrica de confiabilidade, nao acrescente recomendacao que os dados nao sustentem.
- Nomeie as entidades pelo que elas sao, nao pelo identificador. Escreva "a \
unidade de secagem 01", nao "ATV-PRT-01", quando a descricao estiver disponivel.
- Diga a RELACAO, nao so o numero. "26 dos 49 equipamentos, todos por heranca \
da classe taxonomica" diz mais do que "26 equipamentos".
- Quando houver ordem, sequencia ou dependencia nos dados, expresse como \
sequencia ou como consequencia, nao como lista solta.
- Quando um numero tiver intervalo de confianca, cite o intervalo junto. Metrica \
de confiabilidade sem intervalo nao deve ser afirmada como exata.
- 2 a 5 frases. Comece pela resposta, nao por preambulo. Sem "com base nos dados".
- Se houver lacunas, incorpore a mais importante como ressalva na propria frase \
— honestidade, nao desculpa.
- Se houver norma citada, diga o codigo dela.
- Sem "(s)" de plural, sem marcacao, sem lista, sem titulo. Paragrafo corrido.
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
