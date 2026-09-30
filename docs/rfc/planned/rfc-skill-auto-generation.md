# RFC: Skill Auto-Generation Pipeline

**Data:** 2026-05-31
**Status:** Draft (não implementar agora)
**Pré-requisitos:** Bootstrap estável (✅), ≥50 mistake_notes com padrões (✅ 64), evidência de gap entre erros e skills manuais
**Autor:** Claudio + Kiro

---

## Motivação

O bootstrap diz O QUE fazer/evitar (regras curtas). Skills dizem COMO fazer (procedimentos).
Hoje skills são escritos manualmente quando percebemos um gap. Isso não escala:
- 64 mistake_notes → quantas viraram skills? Poucas.
- Erros recorrentes continuam acontecendo porque a regra curta não basta.

## Princípio

Mesmo padrão do autolearn: mover detecção + geração para o server.
O agente não precisa lembrar de criar skills — o sistema sugere.

---

## Sinais de Gap (detectáveis automaticamente)

| Sinal | Fonte | Threshold |
|-------|-------|-----------|
| Mistake note com ≥3 ocorrências do mesmo `error_pattern` | mistake_notes | 3+ |
| Bootstrap rule com frustration ≥5 | bootstrap profile | frustration ≥5 |
| Sequência de tools repetida em ≥3 sessões | harvest session analysis | 3+ sessões |
| User correction seguida de explicação >200 chars | session JSONL | 1 (sinal forte) |
| Mesmo `memory_search` query em ≥5 sessões | access patterns | 5+ |

---

## Pipeline

```
[1. Detect] ← sinais acumulados (server-side, automático)
     ↓ threshold atingido
[2. Draft] ← LLM gera skill .md (trigger + passos + limites)
     ↓ salva em auto-generated/ com frontmatter {status: draft, uses: 0}
[3. Suggest] ← tool MCP: suggest_skill(context) → retorna draft se match
     ↓ agente decide usar ou não
[4. Track] ← agente reporta: usou? resolveu?
     ↓ uses++, successes++
[5. Promote] ← 3+ usos, >80% sucesso → move para skills/
     ↓ ou
[6. Refine/Retire] ← <50% sucesso → LLM refina OU arquiva
```

---

## Tools MCP (futuras)

### `suggest_skill`
```
Input: {context: "vou postar um PR no GitHub", task_type: "git"}
Output: {skill_name: "pr-approval-flow", status: "draft", content: "...", confidence: 0.85}
        ou null se nenhum skill relevante
```

### `report_skill_outcome`
```
Input: {skill_name: "pr-approval-flow", used: true, resolved: true}
Output: {uses: 4, successes: 3, status: "promote_candidate"}
```

### `list_skill_candidates`
```
Input: {min_signals: 3}
Output: [{pattern: "post sem aprovação", occurrences: 4, suggested_trigger: "antes de gh/glab post"}]
```

---

## Geração do Draft (prompt LLM)

```
You are generating a procedural skill for an AI coding assistant.

Context:
- Error pattern: "{pattern}" (occurred {count} times)
- Correct action: "{correct_action}" (from mistake_notes)
- Related memories: {top_3_related}

Generate a skill in markdown with:
1. **Trigger**: When exactly should this activate? (specific, testable)
2. **Steps**: Numbered procedure (max 7 steps)
3. **Verification**: How to confirm it worked
4. **Limits**: What NOT to do, when to escalate

Format:
# Skill: {name}
**Trigger**: {when}
## Steps
1. ...
## Verification
- ...
## Limits
- ...
```

---

## Onde vive cada parte

| Componente | Localização | Responsável |
|-----------|-------------|-------------|
| Detecção de sinais | mcp-memory-service (server) | Automático (scheduler ou post-commit) |
| Geração de draft | mcp-memory-service (LLM call) | Automático |
| Armazenamento draft | `~/.kiro/skills/auto-generated/` | Filesystem local |
| Sugestão ao agente | tool MCP `suggest_skill` | Server expõe, host decide injetar |
| Tracking de uso | mcp-memory-service (memory_store) | Agente reporta |
| Promoção/retire | Script local ou steering hook | Host-side |

---

## Diferença do auto-evolution-skills.md atual

| Aspecto | Atual (steering) | Proposto (server-side) |
|---------|-------------------|------------------------|
| Detecção | Agente percebe durante sessão | Server detecta via patterns acumulados |
| Geração | Agente escreve na hora | LLM gera offline (background) |
| Dependência | Agente lembrar de seguir o processo | Zero dependência do agente |
| Qualidade | Boa (agente tem contexto completo) | Média (LLM tem só patterns + memories) |
| Cobertura | ~5% das sessões | 100% (automático) |

---

## Riscos

| Risco | Mitigação |
|-------|-----------|
| Skills genéricos/inúteis | Threshold alto (3+ ocorrências), LLM rigoroso, promote gate |
| Explosão de drafts | Max 5 drafts ativos, retire após 7 dias sem uso |
| Conflito com skills manuais | Verificar nome/trigger antes de gerar, não sobrescrever |
| Token budget | Skills sugeridos, não injetados. Agente decide carregar |
| LLM hallucina procedimento errado | Validate gate (3 cenários), user pode vetar |

---

## Critérios para Implementar

Implementar quando TODOS forem verdade:
1. ✅ Bootstrap estável e produtivo
2. ✅ ≥50 mistake_notes com padrões claros
3. ⬜ Evidência de que erros recorrentes NÃO estão virando skills manuais
4. ⬜ Upstream doobidoo disponível (para discutir tool suggest_skill)
5. ⬜ Modelo multilíngue estável (✅ feito hoje)

---

## Referências

- `~/.kiro/skills/auto-evolution-skills.md` — processo atual (steering-based)
- `~/.kiro/skills/self-improvement.md` — meta-skill de auto-melhoria
- RFC 1047 §3 — Consolidation Engine (padrão de background processing)
- Spec harvest-quality-fix — padrão de LLM rewriter para geração de conteúdo
- OpenClaw ClawHub — marketplace de skills com validação
