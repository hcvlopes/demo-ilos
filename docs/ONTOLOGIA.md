# Ontologia — Schema vigente

> Gerado automaticamente por `ontology/export_schema.py`.
> Nao edite manualmente — execute `make schema-doc`.

---

## Labels de no

Total: **36**

| # | Label | Indice (propriedade) |
|---|---|---|
| 1 | `Edificacao` | `id` |
| 2 | `Sistema` | `id` |
| 3 | `Ativo` | `id` |
| 4 | `Equipamento` | `id` |
| 5 | `ParteObjeto` | `id` |
| 6 | `Funcao` | `id` |
| 7 | `ClasseTaxonomia` | `id` |
| 8 | `Fabricante` | `id` |
| 9 | `CentroTrabalho` | `id` |
| 10 | `Equipe` | `id` |
| 11 | `GrupoPlanejamento` | `id` |
| 12 | `Sensor` | `id` |
| 13 | `PontoMedicao` | `id` |
| 14 | `RegistroCondicao` | `id` |
| 15 | `Defeito` | `id` |
| 16 | `EventoFalha` | `id` |
| 17 | `CausaFalha` | `id` |
| 18 | `ModoFalha` | `id` |
| 19 | `MecanismoFalha` | `id` |
| 20 | `NotaManutencao` | `id` |
| 21 | `ConsequenciaNota` | `id` |
| 22 | `OrdemManutencao` | `id` |
| 23 | `Etapa` | `id` |
| 24 | `AcaoTomada` | `id` |
| 25 | `Material` | `id` |
| 26 | `PlanoManutencao` | `id` |
| 27 | `ListaTarefa` | `id` |
| 28 | `ProcessoOperacional` | `id` |
| 29 | `Entrega` | `id` |
| 30 | `Contrato` | `id` |
| 31 | `Indicador` | `id` |
| 32 | `Norma` | `id` |
| 33 | `Requisito` | `id` |
| 34 | `MetricaConfiabilidade` | `id` |
| 35 | `AcaoPermitida` | `id` |
| 36 | `Papel` | `id` |

---

## Tipos de aresta

Total: **44**

| Tipo | Propriedades |
|---|---|
| `CONTEM` | — |
| `PERTENCE` | — |
| `DESEMPENHA` | — |
| `ALIMENTA` | — |
| `REDUNDA_COM` | `capacidade` |
| `CLASSIFICADO_COMO` | — |
| `FABRICADO` | — |
| `MANTIDO_POR` | — |
| `TEM_SENSOR` | — |
| `TEM_PONTO` | — |
| `TEM_REGISTRO` | — |
| `PARA_PONTO` | — |
| `DETECTOU` | — |
| `DETECTADO_EM` | — |
| `IDENTIFICADO_EM` | — |
| `CAUSADO_POR` | — |
| `MANIFESTOU` | — |
| `VIA_MECANISMO` | — |
| `EVOLUIU_PARA` | — |
| `GEROU` | — |
| `RESOLVIDO_POR` | — |
| `OCORREU` | — |
| `ATRIBUIDA` | — |
| `ATRELADA` | — |
| `EXECUTADA_CT` | — |
| `GEROU_ORDEM` | — |
| `EXECUTADA_EM` | — |
| `RESOLVE` | — |
| `TEM_ETAPA` | — |
| `EXECUTADA_POR` | — |
| `USA_MATERIAL` | — |
| `COBRE` | — |
| `USA_LISTA` | — |
| `PLANEJADO_POR` | — |
| `TEM_ENTREGA` | — |
| `VINCULADA` | — |
| `REQUER` | — |
| `MEDE` | — |
| `TEM_REQUISITO` | — |
| `REGULADO_POR` | — |
| `TEM_METRICA` | — |
| `PERMITE` | `viabilidade` |
| `AUTORIZA` | — |
| `APLICAVEL_MODO` | — |

---

## Assinaturas de aresta

Total: **65**

| Origem | Aresta | Destino |
|---|---|---|
| `Edificacao` | `CONTEM` | `Sistema` |
| `Sistema` | `CONTEM` | `Sistema` |
| `Sistema` | `CONTEM` | `Ativo` |
| `Equipamento` | `PERTENCE` | `Ativo` |
| `ParteObjeto` | `PERTENCE` | `Equipamento` |
| `Ativo` | `DESEMPENHA` | `Funcao` |
| `Ativo` | `ALIMENTA` | `Ativo` |
| `Ativo` | `REDUNDA_COM` | `Ativo` |
| `Equipamento` | `CLASSIFICADO_COMO` | `ClasseTaxonomia` |
| `Equipamento` | `FABRICADO` | `Fabricante` |
| `Equipamento` | `MANTIDO_POR` | `CentroTrabalho` |
| `Equipamento` | `TEM_SENSOR` | `Sensor` |
| `Equipamento` | `TEM_PONTO` | `PontoMedicao` |
| `Equipamento` | `TEM_REGISTRO` | `RegistroCondicao` |
| `RegistroCondicao` | `PARA_PONTO` | `PontoMedicao` |
| `RegistroCondicao` | `DETECTOU` | `Defeito` |
| `Defeito` | `DETECTADO_EM` | `Equipamento` |
| `Defeito` | `IDENTIFICADO_EM` | `ParteObjeto` |
| `Defeito` | `CAUSADO_POR` | `CausaFalha` |
| `Defeito` | `MANIFESTOU` | `ModoFalha` |
| `Defeito` | `VIA_MECANISMO` | `MecanismoFalha` |
| `Defeito` | `EVOLUIU_PARA` | `EventoFalha` |
| `Defeito` | `GEROU` | `NotaManutencao` |
| `Defeito` | `RESOLVIDO_POR` | `AcaoTomada` |
| `EventoFalha` | `OCORREU` | `Ativo` |
| `EventoFalha` | `OCORREU` | `Equipamento` |
| `EventoFalha` | `CAUSADO_POR` | `CausaFalha` |
| `EventoFalha` | `MANIFESTOU` | `ModoFalha` |
| `EventoFalha` | `VIA_MECANISMO` | `MecanismoFalha` |
| `EventoFalha` | `IDENTIFICADO_EM` | `ParteObjeto` |
| `EventoFalha` | `GEROU` | `NotaManutencao` |
| `EventoFalha` | `RESOLVIDO_POR` | `AcaoTomada` |
| `NotaManutencao` | `ATRIBUIDA` | `Ativo` |
| `NotaManutencao` | `ATRIBUIDA` | `Equipamento` |
| `NotaManutencao` | `ATRELADA` | `ConsequenciaNota` |
| `NotaManutencao` | `EXECUTADA_CT` | `CentroTrabalho` |
| `NotaManutencao` | `GEROU_ORDEM` | `OrdemManutencao` |
| `OrdemManutencao` | `ATRIBUIDA` | `Ativo` |
| `OrdemManutencao` | `EXECUTADA_EM` | `Equipamento` |
| `OrdemManutencao` | `RESOLVE` | `Defeito` |
| `OrdemManutencao` | `RESOLVE` | `EventoFalha` |
| `OrdemManutencao` | `TEM_ETAPA` | `Etapa` |
| `Etapa` | `EXECUTADA_POR` | `Equipe` |
| `Etapa` | `USA_MATERIAL` | `Material` |
| `PlanoManutencao` | `COBRE` | `Ativo` |
| `PlanoManutencao` | `COBRE` | `Sistema` |
| `PlanoManutencao` | `USA_LISTA` | `ListaTarefa` |
| `PlanoManutencao` | `GEROU_ORDEM` | `OrdemManutencao` |
| `Ativo` | `PLANEJADO_POR` | `GrupoPlanejamento` |
| `Sistema` | `PLANEJADO_POR` | `GrupoPlanejamento` |
| `Edificacao` | `PLANEJADO_POR` | `GrupoPlanejamento` |
| `Equipamento` | `PLANEJADO_POR` | `GrupoPlanejamento` |
| `NotaManutencao` | `PLANEJADO_POR` | `GrupoPlanejamento` |
| `OrdemManutencao` | `PLANEJADO_POR` | `GrupoPlanejamento` |
| `Contrato` | `TEM_ENTREGA` | `Entrega` |
| `Entrega` | `VINCULADA` | `ProcessoOperacional` |
| `ProcessoOperacional` | `REQUER` | `Funcao` |
| `Indicador` | `MEDE` | `ProcessoOperacional` |
| `Norma` | `TEM_REQUISITO` | `Requisito` |
| `Equipamento` | `REGULADO_POR` | `Norma` |
| `ClasseTaxonomia` | `REGULADO_POR` | `Norma` |
| `ClasseTaxonomia` | `TEM_METRICA` | `MetricaConfiabilidade` |
| `ClasseTaxonomia` | `PERMITE` | `AcaoPermitida` |
| `AcaoPermitida` | `APLICAVEL_MODO` | `ModoFalha` |
| `Papel` | `AUTORIZA` | `AcaoPermitida` |

---

*Banco nao disponivel — schema gerado a partir de `ontology/schema.py` (modo offline).*
