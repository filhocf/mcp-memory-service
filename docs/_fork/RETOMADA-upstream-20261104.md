# RETOMADA — integração upstream no fork (04/nov/2026)

## Estado

- Repositório: `~/git/mms/mms`
- Branch de trabalho: `integration/upstream-20261104`
- `main` permanece intacta em `f2cbee833f9092ec5aa85ffaaf48c9c685ea1f24`.
- `github/main` está alinhada com a `main` local.
- `upstream/main`: `a2ee57d3fbea19b7d9a1148c6de701830ae98415`.
- Divergência: fork `510` commits à frente e `52` atrás do upstream.
- Árvore de trabalho: limpa.
- Backups: `backup/pre-upstream-20261104-221334` e `backup/pre-upstream-20261104-221558`.
- VPS: não alterada.

## Decisões fixadas

1. O fork é a linha viva; upstream é fonte de novidades, não dependência de merge imediato.
2. Não alterar `main` até a integração ser validada.
3. Não atualizar a VPS antes de commit/push e testes verdes no fork.
4. Resolver por composição, nunca usar `ours`/`theirs` cegamente.
5. Preservar as capacidades fork-only: síntese/limpeza/identidade/deduplicação/learning-loop de beliefs e escopo por `store`.
6. Incorporar upstream: locks fora do event loop, operações idempotentes, `as_of`/supersessão e reconstrução de entidades.

## Conflitos

- `src/mcp_memory_service/consolidation/belief_service.py`
- `src/mcp_memory_service/server/handlers/memory.py`
- `src/mcp_memory_service/storage/mixins/retrieve.py`

## Ordem dos gates

1. G0: análise arquitetural independente por arquivo e invariantes.
2. G2: merge em branch de integração; resolução por fatia sem editar `main`.
3. G3: testes focados de beliefs, store, `as_of`, supersessão e handlers.
4. G4: review adversarial independente; procurar perda de campos, locks, cursores e proveniência.
5. G5: suíte ampla, changelog e verificação de diff/artefatos.
6. G6: commit/push em `github/main`; verificar remoto.
7. VPS: backup `VACUUM INTO`, contagem antes/depois, fast-forward, instalação editável sem remover ML, restart e health check.

## Falhas de infraestrutura

- Delegações com modelo DeepSeek falharam por parâmetro incompatível: `reasoning_effort=medium` não é aceito; opções aceitas pelo provedor incluem `low`, `high`, `xhigh`, `max` ou inteiro 1–100.
- A falha não invalida o gate; deve-se reexecutar com modelo/parâmetro compatível ou cumprir o gate manualmente e registrar a intervenção.

## Próximo passo exato

Concluir G0 com dois agentes independentes (arquiteto e revisor), ou registrar a indisponibilidade e analisar os três conflitos em cópias isoladas. Depois aplicar a resolução na branch `integration/upstream-20261104`, nunca em `main`.

## Intervenções

- G0 arquitetos/revisor: duas execuções falharam antes de iniciar por `reasoning_effort=medium` incompatível com o provedor `deepseek_v41`. G0 foi cumprido localmente com análise dirigida; a delegação não é pré-requisito.

## Diário de gates

| Gate | Estado | Evidência |
|---|---|---|
| G0 | concluído por intervenção local | delegações falharam por infraestrutura; invariantes e escopo foram confirmados por análise Git dirigida |
| G1 | decidido | regras fork-first e invariantes fixadas acima |
| G2 | pendente | branch criada; merge ainda não reaplicado nesta branch |
| G3 | pendente | — |
| G4 | pendente | — |
| G5 | pendente | — |
| G6 | pendente | — |
| VPS | bloqueado por G2–G6 | nenhuma alteração executada |
