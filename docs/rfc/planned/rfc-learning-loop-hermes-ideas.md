# RFC: Learning-loop — ideias absorvidas do Hermes Agent (Nous Research)

**Status:** planned (backlog / item futuro)
**Data:** 2026-10-04
**Origem:** análise do `NousResearch/hermes-agent` + `hermes-agent-self-evolution` (curadoria W15). Relatório: `~/.kiro/tmp/analise-hermes.md`. Memória: hash 58108aca.
**Relação:** alimenta `rfc-learning-loop` (guarda-chuva) + `rfc-skill-auto-generation` + ADR-0005 (métrica).

## Contexto

O Hermes implementa, em produção e com anos de polimento, o learning-loop de 3 camadas que
planejamos. Analisamos o código. Veredito: **loop maduro, store raso.** O comportamento de
aprender (gatilhos, fork de review, curator, skills auto-geradas, self-evolution DSPy+GEPA) é
excelente; mas o armazenamento de memória persistente é **2 arquivos .md (~3.5KB total:
MEMORY.md 2200 + USER.md 1375 chars), sem embeddings, sem busca semântica, sem belief
store/confidence/decay/grafo.**

Nós somos o inverso: store rico (24k memórias, busca semântica + FTS + grafo, 2.6k beliefs com
confidence/decay/consolidação), loop ainda em construção. **Não adaptar nosso projeto ao deles
(seria downgrade). Absorver o LOOP deles sobre o NOSSO store.**

### Insight de produto
O Hermes **se beneficiaria do nosso produto**: o teto de ~3.5KB + ausência de recuperação
semântica é o gargalo deles. Um agente MCP-capable (o Hermes é) poderia usar o mcp-memory-service
como backend de memória de longo prazo. Isso valida o arco **ingestão multi-agente / portabilidade**
("use in any agent" inclui agentes como o Hermes). O mcp-memory-service é a camada de memória
profunda que loops rasos não têm.

## Ideias absorvíveis (padrões, NÃO código — stack e licença divergem)

### 1. ⭐ Catálogo anti-padrões "NÃO capturar" (esforço BAIXO, ROI alto)
O `_DO_NOT_CAPTURE_BLOCK` deles lista o que NUNCA virar memória: afirmação negativa sobre
ferramenta ("X não funciona" — vira refusal auto-citada), narrativa one-off, erro transiente
resolvido, **sequência de tentativas falhas vestida de "workflow recomendado"**. Encaixe:
reforçar `harvest/triage.py` + classifier com esse catálogo. Valida o que já fazemos.

### 2. ⭐ Gatilho por SINAL, não por tempo (MÉDIO)
Eles disparam consolidação por contadores de atividade (N turnos de usuário / N iterações de
tool), não por relógio. Encaixe: usar `usage_events` (telemetria) para disparar consolidação por
sinal — N stores novos, N buscas-sem-hit. Conecta RFC-MM-01 + scheduler.

### 3. ⭐ Holdout "só promova se melhorou" (MÉDIO-ALTO, estratégico)
O self-evolution só aceita um prompt/skill evoluído se um conjunto de **holdout melhora** na
métrica (LLM-judge multidimensional: correctness/procedure/concisão). Encaixe: **operacionaliza
o ADR-0005** (métrica de assertividade) como GATE de verdade — só promover belief/consolidação
se a métrica não piora. É a peça que fecha nosso ciclo de feedback com prova. Absorver o PADRÃO
de eval+holdout, NÃO o DSPy+GEPA como dependência.

### 4. Ponte memória→skill (ALTO, vira RFC própria)
Belief de alta confiança + recorrente → candidato a skill. Nós detectamos (temos confidence);
o harness (Kiro) materializa a skill. Divisão: serviço sinaliza, agente cria.

### 5. Contrato de forma da lição (BAIXO)
Lição = regra imperativa + UMA cláusula de porquê (o mecanismo). Sem narrativa, PR#, data, quote.
"Mesma lição 2x = UMA regra." Fix in place, não append "UPDATE: actually...". Encaixe: `rewriter.py`.

## O que NÃO copiar
- Fork cache-parity de review (pressupõe SER o agente que controla os turnos — nós somos server passivo).
- DSPy+GEPA como dependência (otimiza prompts, não memória; absorver só o padrão de eval/holdout).
- Curator de skills umbrella (não hospedamos skills).
- Store .md plano (é inferior ao nosso belief store — seria downgrade).

## Próximo passo
Backlog. Quando o learning-loop voltar ao foco: começar pelos itens 1 e 3 (anti-padrões + holdout),
que são os de maior razão valor/esforço e conectam com o que já temos (triage + ADR-0005).
