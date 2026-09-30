# G0 — Design do I2 (design-extractor) — mcp-memory-service harvest

**Data:** 2026-09-30 · **Autor:** Claudio + Zero · **Fase:** G0 (investigação/design, sem código de produção)
**Referências:** RFC `rfc-harvest-design-extraction.md` v0.4 · issue #1346 · Phase 0 coverage (#1350) + I0-lang · parser SQLite/discovery (#1378 merged, #1379 approved)

> Este é o G0: mapear o terreno e definir o contrato do extractor ANTES de escrever código. Não empilha sobre o #1379 (ainda não mergeado). Vira PR só depois do #1379 mergear e de trazer os números de cobertura (padrão "bring numbers first").

## 1. O gargalo (verificado no código, 30/set)

`harvest/extractor.py` `PatternExtractor.extract()`:
- `MIN_TEXT_LENGTH = 30`, `DEFAULT_MIN_CONFIDENCE = 0.75`.
- Casa **regex de frase-gatilho** per-locale (`load_patterns`), boosta confiança por nº de matches, aplica gate 0.75.
- **Consequência:** um bloco de análise longa de design (RFC, trade-off, investigação) que NÃO contém frase-gatilho ("decidi", "bug era", "causa raiz") produz **0 candidatos**, mesmo sendo o conteúdo mais valioso. É o coverage gap do #1346 medido pelo Phase 0.

## 2. Infra reutilizável (não reinventar)

- **`harvest/rewriter.py` `HarvestRewriter`** — LLM, lazy-init, cadeia de providers (`HARVEST_LLM_PROVIDERS`), **já resolve locale via `get_active_locales()`** (veio do #1382). É a base do design-extractor: mesmo provider chain, mesmo locale.
- **`reasoning/nli.py` NLIClassifier backend `cascade`** (#1215) — se o extractor precisar separar "decisão tomada" vs "alternativa descartada" via entailment, já existe e é multilíngue via LLM.
- **`harvester._get_rewriter()`** — o wiring lazy já está lá.

## 3. Onde o design-extractor se pluga

No `harvester._harvest_file` / no fluxo de extração, como **caminho alternativo** ao PatternExtractor, NÃO substituto:
- Para cada bloco de texto: PatternExtractor roda como hoje (barato, gate-gatilho).
- **SE** o bloco excede `MCP_HARVEST_DESIGN_MIN_CHARS` (default a definir, ex. 400) **E** o PatternExtractor não produziu candidato (ou produziu poucos), **ENTÃO** rotear para o design-extractor: prompt LLM "extraia decisão + porquê + trade-offs" via HarvestRewriter, sob o locale resolvido.
- Candidato do design-extractor carrega proveniência `harvest:method:llm` + `harvest:mode:design` (RFC-harvest-provenance).

## 4. Contrato (a detalhar em G3/G4)

- **Entrada:** ParsedMessage com texto longo que o PatternExtractor descartou.
- **Saída:** 0+ HarvestCandidate com o raciocínio extraído (não só a conclusão), tipo apropriado (decision/learning/pattern), confiança, proveniência mode:design.
- **Locale:** via `get_active_locales()` — o extractor honra o locale do operador (R3.1 v0.4), NÃO decide por fração de corpus.
- **Opt-in:** `MCP_HARVEST_DESIGN_ENABLED` default off até validação de yield (R5).
- **Ruído:** taxa de adoção contada dia-1 (candidatos gerados vs sobreviventes ao dedup) — R6; 3º estado do dashboard (R6.1).

## 5. Gate (disciplina R10 + "bring numbers first")

ANTES de virar PR:
1. #1379 mergeado (o Phase 0 com idioma que mede o gap está no upstream).
2. Rodar o Phase 0 sobre sessões densas reais → quantos blocos longos são descartados pelo PatternExtractor, por tipo e locale (já temos a matriz: 53-75% dropado, ~85-89% pt-BR neste host).
3. Piloto do design-extractor protótipo contra 5-10 sessões densas → medir memórias densas prestáveis vs ruído, comparar com o que o harvest atual capturou.
4. Só então: alternativas mais baratas que LLM (R2.1 — melhor trigger-set OU parsear ToolResults) podem fechar parte do gap; o LLM-extractor só se justifica se o gap sobreviver a elas.

## 6. Dependências e ordem

- **Depende de #1379** (Phase 0 idioma + SQLite) — aguardando merge do Henry.
- **I1** (visibilidade thinking/ToolResult no parser) vem antes ou junto: hoje esses blocos são dropados no nível de mensagem sem inspecionar texto; o design-extractor precisa vê-los.
- **Reusa #1382** (MCP_LOCALE no harvest) — já mergeado, já na nossa main.

## 7. Próximo passo

Aguardar #1379 mergear → rodar Phase 0 e trazer os números por-tipo/locale à issue #1346 → decidir entre alternativas baratas (R2.1) e o LLM-extractor → G3 (testes RED do contrato) → G4 → PR. Este doc é o G0; não há código de produção nesta fase.
