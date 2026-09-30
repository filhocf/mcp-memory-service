# Pilha de PRs — mcp-memory-service fork (runbook)

**Criado:** 03/set/2026 · **Atualizado:** 30/set/2026 · **Estratégia:** PR sai de `upstream/main` limpo · **Base:** `upstream/main` (GitHub, v11.14.0+)

> **Escopo deste doc:** o PROCESSO de transporte fork→upstream (mecânica de branches, protocolo de saúde, disciplina de transporte). **NÃO** duplica estado dos arcos (isso é `ESTADO.md`/`ARCOS.md`) nem backlog de épicos (`roadmap.md`). Regra: mexeu → documenta no lugar certo.

## Estado atual (30/set)
- **Fila Henry: 0 PRs nossos abertos.** main fork sincronizada com upstream (fork-only à frente, 0 atrás).
- **PRs de terceiros na nossa área (só observar, aguardam Henry):** #1391 (timkjr, `MCP_DECAY_ENABLED` — CLEAN+greptile-APPROVED, toca consolidation/, fecha furo do nosso arco rating; timkjr resolveu, não pegamos).
- **Próximo PR nosso:** arco ingestão multi-agente, Fase 0 (Kiro→YAML) — aguarda discussion #1393.

## Topologia
```
upstream/main ──→ pr/<feat> ──(Henry mergeia)──→ upstream/main
                                    │ (git merge upstream/main, NUNCA cherry-pick)
                                    ▼
                                fork/main  ← LINHA VIVA (serviço roda daqui)
```
- **fork/main = upstream/main + camada nossa** (docs/rfc, docs/_fork, feats fork-only). Serviço roda daqui.
- **pr/<feat> sai do upstream/main limpo** (senão o PR carrega nossos docs/plugins e vaza no PR do Henry).
- Feat aprovada volta ao fork/main via **merge do upstream**, nunca cherry-pick (evita duplicata).
- **Remotes:** `upstream`=GitHub doobidoo (origem, fetch) · `github`=fork filhocf (push aqui). Push só no fork.

## Disciplina de transporte (regra do Claudio)
1. **VERIFICAR o upstream antes de transportar** — checar `arquivo:linha`. Não assumir que falta nem que já tem. (Evita submeter fix que o upstream já tem.)
2. **REESCREVER, não cherry-pick cru** — o upstream anda rápido; adaptar a feature ao código atual.
3. **Seguir o GATE** (dev-workflow): G0 arch → G3 testes RED → G4 GREEN → G5 review. TDD, não improviso.
4. **1 PR por vez**, escopo mínimo, 1 assunto. Fila do Henry é serial.
5. **E2E real antes de PR** (mocks escondem bugs — lição #1265, tupla que mock mascarava).
6. **Doc no MESMO commit** (anti-drift). >1 arquivo → gate.
7. **Nunca self-merge.** Aguardar o Henry (padrão dele).

## Protocolo de saúde (a cada branch nova)
1. Implementar a feature.
2. Testes da feature: `.venv/bin/python -m pytest tests/test_<feature>.py -q`
3. Regressão da área vs baseline: `pytest tests/ -q -k "harvest or nli or reasoning or belief"` → 0 falhas.
4. Só então a próxima branch.
- Interpretador: `~/git/mcp-memory-service/.venv/bin/python` (mesmo do serviço, venv ONNX-only, sem torch).

## Fluxo de PR
1. `git fetch upstream` → branch `pr/<feat>` de `upstream/main` limpo.
2. Implementar (gate) → push no `github` → `gh pr create --repo doobidoo/mcp-memory-service`.
3. pr-review skill: responder Greptile/Actions, corrigir, re-submeter até verde.
4. Henry mergeia → `git checkout main && git merge upstream/main` (traz a feat oficial, remove a fork-only).

## Mandato de merge (co-maintainer)
Escopo: `quality/` + `handlers/` + `harvest/`. Fora disso (web/, consolidation/, storage/) = opinião/review, não merge. Ver skill `memory-service-maintainer`.

## Referências
- Backlog de épicos: `roadmap.md` · Estado dos arcos: `ARCOS.md`/`ESTADO.md`
- Arquitetura: `reference-pipeline.md` · Índice RFCs: `../rfc/_index.md`
- Reconciliação fork↔upstream (histórica): `reconciliacao-v11.10.0.md`
