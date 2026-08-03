# Contexto do projeto

Demo de agentes sobre grafo de conhecimento de ativos industriais, para o
Congresso ILOS. Dois setores de referência: armazenagem de grãos (agro) e
almoxarifado/frota de distribuidora de energia (elétrico).

A tese que a demo prova: a camada semântica ancorada em norma é pré-requisito
da IA industrial. O grafo declara dependência, norma aplicável e ação
permitida — coisas que dashboard não declara.

## Regras invioláveis

1. **Intenção versionada primeiro; Cypher gerado só como rede.**

   A regra original era "o LLM nunca escreve Cypher". Ela foi relaxada por
   decisão do dono do produto, para ampliar o alcance das perguntas. O que
   vale agora:

   - Se alguma intenção de `intents/` cobre a pergunta, é ela que responde.
     Travessia versionada, revisada e testada tem precedência **sempre**.
   - Só quando nenhuma cobre, o LLM escreve Cypher (`api/consulta_livre.py`).
   - Essa execução é **somente leitura imposta pelo servidor**
     (`GRAPH.RO_QUERY`), não por checagem no cliente. Há guarda sintática
     antes, mas ela existe para dar mensagem melhor — a garantia é do banco.
   - O Cypher gerado **entra no envelope** e aparece na tela. Consulta que
     ninguém pode auditar não vai para produção.
   - A resposta declara qual caminho respondeu (`caminho`), e a interface
     mostra isso. As duas não têm o mesmo grau de confiança.

   Nenhuma rota da API aceita Cypher vindo do cliente. O que mudou é quem
   escreve a consulta internamente, não a fronteira da API.

2. **Toda intenção devolve envelope de evidência completo**: afirmacao, nos,
   arestas, calculos, normas, lacunas. Intenção sem envelope não passa no
   teste e não entra.

3. **Vocabulário setorial nunca entra no grafo.** Rótulo de exibição resolve
   em tempo de renderização a partir de `vocab/perfis/`. Nós e arestas usam
   nomes neutros. Existe teste que falha se "safra", "silo", "religamento" ou
   equivalente aparecer em propriedade de nó.

4. **Códigos ISO 14224 vêm exclusivamente de `fixtures/iso14224/`.** Nunca
   inventar, inferir ou completar código de modo, causa, mecanismo ou classe
   taxonômica. Se falta um código, pare e pergunte.

5. **Nenhum tipo de nó ou aresta exclusivo de um setor.** Se o elétrico
   precisar de algo que o agro não usa, generalize o nó. Duplicar por setor
   invalida a tese do projeto.

6. **Seeders são idempotentes.** Rodar duas vezes produz o mesmo grafo.

7. **λ por hora de operação, nunca por hora de calendário.** No agro a
   exposição concentra em safra; ignorar isso produz métrica indefensável.

8. **Toda métrica de confiabilidade exibida acompanha intervalo de
   confiança.** λ sem IC não é exibível.

## Ontologia

Schema vigente em `docs/ONTOLOGIA.md`, gerado por `ontology/export_schema.py`.
Consulte antes de qualquer alteração. Nunca altere schema sem migration
numerada e idempotente em `ontology/migrations/`.

## O que não fazer

- Não criar abstração para caso de uso que ainda não existe.
- Não modelar `Material`, `Carga` ou refinamento de `AcaoPermitida` além do
  mínimo especificado. Estão congelados até haver cliente real.
- Não usar dado de cliente real. Todo dataset é sintético ou anonimizado.
- Não commitar credencial. Segredos por variável de ambiente.

## Comandos

- `make up` — sobe o grafo
- `make seed-agro` / `make seed-eletrico`
- `make test`
- `make schema-doc` — regenera docs/ONTOLOGIA.md
