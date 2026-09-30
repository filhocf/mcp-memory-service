# Padrão: Experimento Exploratório antes da RFC (memory-service D*)

**Criado:** 18/set/2026 (Claudio + Zero) · **Contexto:** RFCs Mnemosyne D1-D9 no fork mcp-memory-service.

## Princípio (decisão do Claudio, 18/set)

Antes de amadurecer/propor uma RFC ao Henry, rodar um **experimento exploratório
read-only** no banco de produção real. Motivo comprovado no mesmo dia:
- **D2**: RFC estimava −73MB de ruído; experimento real mostrou candidate_ratio 3%
  (~0.2MB) + 2 secrets REAIS. Reposicionou a RFC (segurança, não disco).
- **D1**: experimento confirmou 84MB reais + achou que o ganho exige a migração R5
  (não a config), corrigindo o escopo.
- **D3**: só 15% das queries reais têm intenção detectável; regex precisa calibrar.

O experimento (a) dá visão real, (b) corrige a RFC com número, (c) vira evidência
forte para o Henry (perfil: não aceita sem benchmark/dado). Custo baixo, read-only.

## Regra
- Experimento = script standalone read-only (não toca o serviço, não escreve no banco).
- Salvar o achado na própria RFC (seção "🔬 Experimento exploratório (data)").
- Ajustar prioridade/escopo da RFC conforme o dado (rebaixar se o ganho não se confirma).

## Mapa dos experimentos D4-D9 (a rodar)

| RFC | Experimento read-only | Mede |
|-----|----------------------|------|
| D4 ranking | distribuição idade×tipo de memória; simular decay uniforme vs Weibull-por-tipo numa amostra | quantas preferências "envelhecem cedo demais" |
| D5 working-memory | quantas memórias relevantes de sessão longa NÃO foram pegas no startup pull | tamanho do recall gap |
| D6 persona-tier | extrair (rule-based) persona candidata das memórias preference/persona; comparar com persona.md | cobertura da identidade auto-derivável |
| D7 delta-sync | custo do sync atual (MB, freq) + quantas memórias diferem entre máquinas | economia delta vs full-file |
| D8 multimodal | 1 provider de visão no infográfico Debian real → descrição → memória buscável | PoC do caso ativo |
| D9 importers | inspecionar formato da memória holográfica do Hermes (T'Pol) → contar entradas importáveis | tamanho do acervo importável |

## Já feitos
- ✅ D1 quantization (18/set) — G0 viabilidade; migração R5 é o ganho local; sessão dedicada
- ✅ D2 hygiene (18/set) — candidate_ratio 3%, despriorizada (segurança > disco; achou 2 secrets)
- ✅ D3 query-intent (18/set) — só 15% intenção detectável, rebaixada até classificador calibrar
- ✅ D4 ranking (19/set) — 82% do acervo >30d; 22% estáveis+antigas penalizadas pelo decay uniforme → Weibull-por-tipo tem ganho real
- ✅ D5 working-memory (19/set) — recall gap 99% (pull único traz 10 de 717 recentes) → valida camada hot
- ✅ D6 persona-tier (19/set) — 74 memórias de identidade → persona auto-derivável (não precisa persona.md manual)
- ✅ D7 delta-sync (19/set) — divergência 7% entre 3 hosts; full-file transfere ~432MB p/ 7% real → delta economiza ordem de magnitude

## Pendentes (BLOQUEADOS por recurso — verificado 20/set)
- ⏳ D8 multimodal — infográfico Debian ESTÁ local (~/git/debian-infographic, PNGs+SVG+JSONs). BLOQUEIO: sem provider de visão (nenhum modelo vision no Ollama; sem API key OpenAI/Anthropic/Gemini nos envs). PRÉ-REQ: `ollama pull llava`/`moondream` (~4GB) OU configurar API de visão. Decisão do Claudio.
- ⏳ D9 importers — inspecionar formato da memória holográfica do Hermes. BLOQUEIO: precisa acesso ao Hermes/T'Pol (VPS). PRÉ-REQ: dump/amostra do formato holographic do Hermes.

## Scripts
Os exploradores vivem em ~/.kiro/tmp/ (efêmeros). A LÓGICA/achado fica na RFC (durável).
D3: explore_d3.py (classifica memory_gaps). D2: audit_noise.py (já removido, lógica na RFC).
