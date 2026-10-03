# Metodologia de Fork de Longo Prazo

> Como manter o fork sem perder trabalho, triar a evolução do upstream, e landar nossas feats.
> Fonte única de rastro: `LEDGER-feats.md` + `ORFAOS.md` (este diretório). Espelho em memory-service tag `mms-ledger`.
> **Invariante:** nenhum commit fork-only existe sem uma linha no LEDGER dizendo onde está e se já voltou à main.

## Ritual 1 — Triar o upstream (upstream → fork)
**Quando:** 1×/semana OU quando `behind > 20`. Persiga `upstream/main`, não cada tag de release.

```bash
git fetch upstream --tags
git rev-list --count main..upstream/main    # behind
git log --oneline main..upstream/main        # o que vem
```

**Para cada bloco de commits, classificar:**
- 🟢 **ABSORVER** — feature/fix que não toca nossa camada → entra no merge.
- 🟡 **CONFLITA** — toca arquivo com feat fork-only nossa → reescrever NOSSA feat sobre o código novo (nunca cherry-pick cego).
- 🔴 **NOS OBSOLETA** — upstream implementou o que era nossa feat/RFC → retirar nossa versão, LEDGER `SUPERSEDED-BY-UPSTREAM`, RFC planned→implemented ou arquivar.
- ⚪ **IGNORAR** — docs/CI deles.

**Passos:**
1. `safety/<AAAAMMDD>-pre-sync` (tag anotada, não branch) antes do merge.
2. `git merge upstream/main` (NUNCA rebase da main — ela é publicada e roda o serviço).
3. Protocolo de saúde: pytest da área vs baseline, 0 falhas.
4. Atualizar ESTADO.md/ARCOS.md/LEDGER **no mesmo commit** do merge (anti-drift).
5. **Varredura de obsolescência:** p/ cada feat fork-only viva, "o upstream já faz isto?" — checar arquivo:linha (verificar, não assumir).

## Ritual 2 — Landar nossas feats (fork → upstream)
**Discussion/RFC primeiro** quando: muda contrato público, adiciona dependência, toca >1 módulo, ou é visão. **PR direto** quando: bug isolado, fix de 1 arquivo, feature pequena auto-contida com teste.

**Fatiar:** 1 PR = 1 assunto, sai de `upstream/main` LIMPO. FEAT serial (fila do Henry); BUG em paralelo.

**Rastrear estado no LEDGER:** IDEIA → DESIGN → IMPL-FORK → PR-ABERTO → MERGED | FORK-ONLY-PERMANENTE | SUPERSEDED-BY-UPSTREAM.

## Ritual 3 — Não perder trabalho
**Em todo sync/merge/reset que reescreva a main:**
1. Backup = tag `safety/<data>-<motivo>` (retenção 30d), não branch.
2. Rodar o **detector de órfãos**:
```bash
for ref in $(git for-each-ref --format='%(refname:short)' refs/tags refs/heads | grep -iE "backup|archive|safety"); do
  n=$(git rev-list --count "$ref" --not main upstream/main 2>/dev/null); echo "$n|$ref"
done | sort -t'|' -rn
```
3. Qualquer ref com `n>0` → tem trabalho não-relandado → **PARE** e registre veredito no `ORFAOS.md` (RELAND/SUPERSEDED/DESCARTAR) antes de seguir.
4. Mensal: detector + reconciliar LEDGER. Órfão `salvo=sim` há >30d → tag deletável.

## Convenção de branches/tags
| tipo | formato | objeto | retenção |
|------|---------|--------|----------|
| linha viva | `main` | branch | eterna |
| PR em voo | `pr/<slug>` (de upstream/main limpo) | branch | deleta ao merge/close |
| feat/fix em dev | `feat/<slug>` `fix/<slug>` | branch | deleta ao landar na main |
| design | `design/<slug>` | branch | enquanto RFC viva |
| backup pré-operação | `safety/<AAAAMMDD>-<motivo>` | **tag anotada** | 30d, deleta se main conteve |
| arquivo c/ órfão | `archive/<AAAAMMDD>/<slug>` | **tag anotada** | eterna SE #únicos>0 |

**Regra de ouro:** backup só vira `archive/` permanente se o detector provar `#únicos>0`. Snapshot 100% absorvido pela main = lixo, deletar.

## Durabilidade cross-máquina
Ao fechar veredito de órfão ou landar feat: `memory_store` tag `mms-ledger` + commit hash. As 3 máquinas compartilham o banco de memória, não o git local — o rastro sobrevive a reset do working tree.
