# Progresso por fase

| Fase | Status | Data | Resumo |
|---|---|---|---|
| F0 — Scaffolding | Concluída | 2026-08-01 | Estrutura, docker-compose, Makefile, CLAUDE.md, deps, 7 testes verdes |
| F1 — Ontologia | Concluída | 2026-08-01 | Schema completo (35 labels, 37 rel types, 59 assinaturas), migration 001, export_schema, 14 testes |
| F2 — Calibração | Concluída | 2026-08-01 | Gerador Poisson não-homogêneo, estimador MLE com IC χ², fixtures ISO 14224 (15 classes, 16 modos, 12 causas, 18 mecanismos), 10 testes de calibração |
| F3 — Dataset agro | Concluída | 2026-08-02 | Seeder agro com 28 equipamentos, 5 sistemas, hierarquia física completa, eventos Poisson + workflow manutenção, 14 testes |
| F4 — Intenções | Concluída | 2026-08-02 | Contrato base, registry, 3 intenções transversais (explicar_defeito, acoes_permitidas, historico_equipamento), envelope de evidência, 12 testes |
| F5 — Escore de risco | Concluída | 2026-08-02 | Motor P(falha)×impacto×(1-redundância), intenção ativos_em_risco_por_processo, IC propagado, 31 testes |
| F6 — API | Concluída | 2026-08-02 | FastAPI (POST /pergunta, GET /intencoes, GET /saude), orquestrador LLM Anthropic, classificação de intenção tipada, 18 testes |
| F7 — UI | Concluída | 2026-08-02 | SPA self-contained (web/index.html), chat + painel de evidência, grafo SVG, cálculos com IC, 15 testes |
| F8 — Ação permitida | Concluída | 2026-08-02 | Catálogo AcaoPermitida (10 ações, 3 tipos), Papel autorizador (3 níveis), viabilidade por complexidade, migration 002, 24 testes |
| F9 — Elétrico | Concluída | 2026-08-02 | Seeder elétrico com 21 equipamentos, 5 sistemas, 7 ativos, hierarquia subestação, perfil uniforme 24/7, topologia ALIMENTA/REDUNDA_COM, catálogo AcaoPermitida, 36 testes |
