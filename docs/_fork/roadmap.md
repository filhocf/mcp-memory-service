# mcp-memory-service — Backlog de épicos (roadmap do fork)

**Criado:** 15/set/2026 · **Atualizado:** 30/set/2026 · **Base:** `upstream/main` (GitHub, v11.14.0+)

> **Escopo deste doc:** o BACKLOG de épicos futuros (o que ainda dá para fazer), com esforço×dificuldade×passos e ordem de ataque. **NÃO** duplica estado — o estado dos arcos vive em `ESTADO.md` (árvore, humano) e `ARCOS.md` (tabela, agente); o estado operacional dos PRs em `pilha-prs-runbook.md`. Regra: mexeu → documenta no lugar certo (estado nos gêmeos ARCOS/ESTADO; backlog aqui).

## Legenda
- **Esforço:** 🟢 baixo (≤1 sessão) · 🟡 médio (1-2) · 🔴 alto (3+ / multi-PR)
- **Dificuldade:** ★ mecânico · ★★ design local · ★★★ arquitetural
- **Dep. Henry:** precisa OK antes (feature grande) ou é contribuição direta

## Ordem de ataque (backlog, quando a fila liberar)
1. **Arco ingestão multi-agente** — Fase 0 (Kiro→YAML golden test) assim que a discussion #1393 destravar. É o foco.
2. **D3 query-intent** PT/EN — quick win, melhora nossa busca (1 PR, 🟢★★).
3. **D1 + D2** — quick wins de disco (quantization + hygiene, −60~80MB).
4. **C (Trilogia RFC-MM)** — bloco grande, Henry validou (#1286). Multi-PR.
5. **G1 kiro-hooks** + arquiteturais (D5/D6/D7) — adoção → malha.

## C. Trilogia RFC-MM (Onda 2 — maior bloco)
RFC `rfc-self-service-memory-intelligence.md`. §1/§2/§4/§5/§7 já no upstream. Falta o background (migrations 013/014/015 + tools memory_facts/memory_gaps + handlers). **Henry VALIDOU no #1286** ("claims hold", escopo = background enrichment, NÃO inter-agent messaging) → pode codar sobre v11.14.0 (base `2e1978d5`).

| # | Épico | O que é | Esf | Dif | Passos |
|---|-------|---------|-----|-----|--------|
| C1 | fact-extraction | job 6h: observação→fato (memory_facts) | 🔴 | ★★★ | 2-3 PR |
| C2 | gap-detection | busca baixa-confiança → lacuna (memory_gaps) | 🔴 | ★★★ | 2-3 PR |
| C3 | feedback-loop | recalibra confiança de belief por uso/rating | 🔴 | ★★★ | 2-3 PR |
| C4 | §6 anti-halluc | abstain/insufficient-evidence no retrieve | 🟡 | ★★ | 1 PR |

## D. Mnemosyne (9 RFCs — inspiradas na ferramenta do Hermes)
Amadurecidas no fork (13/set). Ordem de valor: quantization+hygiene primeiro (disco), depois arquiteturais.

| # | Épico | RFC | O que é | Esf | Dif |
|---|-------|-----|---------|-----|-----|
| D1 | embedding quantization | rfc-embedding-quantization | int8/bit: 82→21MB (int8) ou →3MB (bit). MCP_MEMORY_VEC_TYPE | 🟡 | ★★ |
| D2 | memory hygiene | rfc-memory-hygiene | audit_noise dry-run + clean_noise + secret detection. Ataca FTS | 🟡 | ★★ |
| D3 | query intent | rfc-query-intent | classificação regex PT/EN → ajusta pesos vetor/FTS | 🟢 | ★★ |
| D4 | ranking upgrades | rfc-ranking-upgrades | Weibull decay por tipo + polyphonic recall | 🟡 | ★★★ |
| D5 | working memory | rfc-working-memory | camada quente (TTL, auto-inject, promoção→episodic) | 🔴 | ★★★ |
| D6 | persona tier | rfc-persona-tier | identidade portável auto-gerada + canonical SSOT | 🔴 | ★★★ |
| D7 | delta sync | rfc-delta-sync | event-log delta multi-agente + cripto (malha Zero/T'Pol/Scotty). RFC #1345 v0.3 §8 invariantes | 🔴 | ★★★ |
| D8 | multimodal memory | rfc-multimodal-memory | imagem/vídeo/áudio→texto via visão, sem BLOB | 🔴 | ★★★ |
| D9 | memory importers | rfc-importers | BaseImporter + adaptadores. Par da porta "bring your memory" | 🟡 | ★★ |

## E. Skill auto-generation (cruza skill-curator-mcp)
RFC `rfc-skill-auto-generation.md`. Depende do skill-curator-mcp (nosso), não só do memory-service.

| # | Épico | O que é | Esf | Dif |
|---|-------|---------|-----|-----|
| E1 | skill_scout ampliar fontes | PyPI, npm, awesome-lists | 🟡 | ★★ |
| E2 | sugestão proativa de skill | quando match < limiar | 🟡 | ★★ |
| E3 | gap detection ↔ tasks | correlacionar com tasks executadas | 🟡 | ★★★ |

## G. Client adapters — "traga sua memória" por cliente
Duas metades por harness: **G-adapt (usar)** = cliente usa o serviço como memória nativa, estilo `claude-hooks/` (só Claude Code tem hoje); **G-import (trazer)** = puxar a memória que o cliente já tem (é o D9/importers). *Nota: este grupo é parcialmente absorvido pelo arco ingestão multi-agente — G-adapt = a porta "use in any agent".*

| # | Épico | O que é | Esf | Dif | Dep. Henry |
|---|-------|---------|-----|-----|------------|
| G1 | kiro-hooks | integração Kiro CLI (espelha claude-hooks/) | 🟡 | ★★ | direta |
| G2 | hermes adapter + importer | Hermes usa store + importer holographic (issue #1095) | 🔴 | ★★★ | talvez |
| G3 | openclaw adapter | integração OpenClaw | 🟡 | ★★ | direta |
| G4 | outros | Cursor, Continue, Windsurf, Zed | 🟡 | ★★ | direta |

## H. Issues órfãs upstream (bugs sem dono — contribuição direta)
> Estado das issues muda em ~24h num repo ativo. SEMPRE reler assignee + último comentário antes de pegar.

| # | Issue | Sev | Estado | Ação |
|---|-------|-----|--------|------|
| H1 | #1225 store sem embedding row | high | OPEN, guard já existe | avaliar valor (backfill/detecção) |
| H5 | #1106 API/dashboard sem store | bug | OPEN | web layer, fora mandato |
| — | #1096 rate-limit per-agent | feat | agent_id destravou keying | PR futuro (arco hub) |
| — | #1097 Prometheus/OTel | feat | não implementado | manter, sem urgência |

Fechadas/com dono (não pegar): #1224, #1216, #1102, #1098 (fechamos); #1146 (massimiliano1991).

## Extremos (priorização)
- **Mais fácil:** D3 query-intent, H1 #1225 (avaliar). 🟢★ 1 PR.
- **Mais difícil:** D7 delta-sync (3+ PR ★★★), Trilogia C1-C3 (validada #1286).
- **Maior valor/esforço:** D1 quantization + D2 hygiene (disco).
- **Maior valor estratégico:** D5 working-memory + D6 persona + D7 delta-sync (identidade/malha da tripulação).
