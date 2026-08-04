"""Migration 003 — processo operacional declarativo.

O processo era `{id, descricao}` com um saco plano de funcoes penduradas por
REQUER. Nao dava para perguntar sequencia, gargalo, nem o que para o processo
se uma funcao falhar — porque nada disso estava declarado.

O que esta migration acrescenta, e por que cada coisa:

1. `REQUER` ganha `ordem` e `criticidade`.

   Preferi propriedade de aresta a um no `EstagioProcesso` novo. Duas funcoes
   com a mesma `ordem` ja expressam estagio paralelo, e a criticidade e uma
   propriedade da RELACAO entre processo e funcao, nao da funcao em si: a mesma
   funcao pode ser essencial num processo e auxiliar em outro. Um no novo
   diria menos e custaria mais.

   `criticidade`: 'essencial' (perder para o processo), 'importante' (degrada),
   'auxiliar' (nao impede).

2. `ProcessoOperacional` ganha `regime` e `horas_operacao_ano`.

   O regime de operacao existia so no perfil de Poisson dos seeders. Trazido
   para o grafo, a regra 7 do CLAUDE.md — lambda por hora de OPERACAO, nunca
   de calendario — deixa de ser convencao de codigo e passa a ser fato
   consultavel: da para perguntar por que um processo sazonal de 2.200 h/ano
   nao se compara a um continuo de 8.760 h/ano.

3. `Indicador` ganha `valor_atual`.

   Tinha `meta` e nenhuma medicao, entao "esta atendendo a meta?" nao tinha
   resposta. Sem isso o indicador era decoracao.

4. Nova aresta `ProcessoOperacional -PRECEDE-> ProcessoOperacional`.

   Cadeia entre processos. Sem ela nao se pergunta o que fica a jusante.

Idempotente: so acrescenta indice, e SET de propriedade e idempotente por
natureza. O preenchimento dos valores fica nos seeders.
"""

from db.adapter import create_driver

# Rotulos que passam a ser consultados diretamente por intencao de processo.
LABELS_INDEXADOS = ["ProcessoOperacional", "Funcao", "Indicador"]


def migrate(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> None:
    driver = create_driver()

    with driver.session() as session:
        for label in LABELS_INDEXADOS:
            # Indice ja existente levanta; ignorar e o que torna a migration
            # idempotente (regra 6). Nao ha nada a registrar.
            try:
                session.run(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
            except Exception:  # noqa: BLE001, S110 — indice ja existe
                pass

    driver.close()
    print(f"Migration 003 concluida. {len(LABELS_INDEXADOS)} indices verificados.")


if __name__ == "__main__":
    migrate()
