"""Valida o corpus de exemplos contra o grafo semeado.

Roda toda consulta de fixtures/exemplos_consulta.yaml e reprova a que:
- nao passar na guarda somente-leitura;
- nao executar no banco;
- executar mas nao retornar nenhuma linha.

O terceiro criterio e o que mais pega erro sutil. Um Cypher sintaticamente
valido que devolve vazio — porque errou o sentido de uma aresta, ou o nome de
uma propriedade — ensina o modelo a escrever consulta que nao responde nada.

Uso:
    make exemplos-validar
    python -m scripts.validar_exemplos --jsonl exemplos.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

from api.consulta_livre import ConsultaRecusada, validar_cypher
from api.exemplos import carregar_exemplos
from db.adapter import create_driver


def validar(mostrar_amostra: bool = False) -> int:
    exemplos = carregar_exemplos()
    driver = create_driver()
    falhas: list[str] = []
    vazios: list[str] = []
    total_linhas = 0

    print(f"Validando {len(exemplos)} exemplos contra o grafo...\n")

    with driver.session() as session:
        for ex in exemplos:
            rotulo = ex.pergunta[:62]
            try:
                travessia = validar_cypher(ex.cypher)
            except ConsultaRecusada as e:
                falhas.append(f"{rotulo}\n      guarda recusou: {e}")
                print(f"  RECUSADA  {rotulo}")
                continue

            try:
                linhas = list(session.run_somente_leitura(travessia))
            except Exception as e:  # noqa: BLE001 — qualquer erro do banco reprova
                falhas.append(f"{rotulo}\n      banco: {str(e)[:150]}")
                print(f"  ERRO      {rotulo}")
                continue

            total_linhas += len(linhas)
            if not linhas:
                vazios.append(rotulo)
                print(f"  VAZIA     {rotulo}")
                continue

            print(f"  ok ({len(linhas):3}) {rotulo}")
            if mostrar_amostra and linhas:
                primeira = linhas[0]
                amostra = ", ".join(f"{k}={primeira[k]}" for k in primeira.keys())  # noqa: SIM118
                print(f"            -> {amostra[:110]}")

    driver.close()

    print(f"\n{len(exemplos)} exemplos | {total_linhas} linhas retornadas no total")
    if falhas:
        print(f"\n{len(falhas)} FALHA(S):")
        for f in falhas:
            print(f"  - {f}")
    if vazios:
        print(f"\n{len(vazios)} CONSULTA(S) SEM RESULTADO:")
        for v in vazios:
            print(f"  - {v}")

    if not falhas and not vazios:
        print("\nTodos os exemplos executam e retornam dados.")
        return 0
    return 1


def exportar_jsonl(caminho: str) -> None:
    """Exporta em formato de treino (mensagens de chat)."""
    from api.consulta_livre import _prompt_sistema

    sistema = _prompt_sistema()
    exemplos = carregar_exemplos()
    with open(caminho, "w", encoding="utf-8") as f:
        for ex in exemplos:
            registro = {
                "messages": [
                    {"role": "system", "content": sistema},
                    {"role": "user", "content": ex.pergunta},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {"cypher": ex.cypher.strip(), "motivo": ""},
                            ensure_ascii=False,
                        ),
                    },
                ],
                "categoria": ex.categoria,
            }
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    print(f"{len(exemplos)} exemplos exportados para {caminho}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", help="exporta o corpus para este arquivo e sai")
    parser.add_argument("--amostra", action="store_true", help="mostra a primeira linha de cada")
    args = parser.parse_args()

    if args.jsonl:
        exportar_jsonl(args.jsonl)
        return 0
    return validar(mostrar_amostra=args.amostra)


if __name__ == "__main__":
    sys.exit(main())
