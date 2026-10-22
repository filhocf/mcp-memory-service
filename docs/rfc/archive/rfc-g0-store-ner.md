# GATE 0 — Multi-store Domain NER (read-only investigation)

- **Repo:** `/home/claudio/git/mcp-memory-service-dev` (worktree, branch `feat/harvest-104`, base upstream v11.10.0)
- **Data:** 2026-09-03
- **Decisão prévia:** reescrever como `DomainExtractor` que lê `store_terms.json` + propagar `store` VIA METADATA (NÃO alterar a assinatura pública `extract_entities(content, metadata)`).

---

## 1. Interface atual — `DomainExtractor` Protocol e `EntityExtractor`

Arquivo: `src/mcp_memory_service/reasoning/entities.py`

- **`Entity`** (dataclass) — `entities.py:16-20`: campos `name: str`, `entity_type: str`, `source: str` (`content|metadata|config|domain`).
- **`DomainExtractor` (Protocol, `@runtime_checkable`)** — `entities.py:23-31`:
  - Assinatura única: `def extract(self, content: str, metadata: dict | None = None) -> list[Entity]: ...` (`entities.py:31`).
  - **O `store` NÃO faz parte da assinatura** → o único canal para o extractor saber o store é `metadata`.
- **`EntityExtractor.extract_entities(content, metadata)`** — `entities.py:51`:
  - `metadata = metadata or {}` (`entities.py:52`).
  - Extrai @mentions (person), #hashtags (tag), URLs, paths, tags de metadata.
  - **Custom terms (upstream)** — `entities.py:84-90`: importa `MCP_ENTITY_CUSTOM_TERMS` de `..config`, split por vírgula, e para cada termo faz match com **word-boundary**:
    ```python
    if re.search(r'(?<![a-zA-Z0-9_-])' + re.escape(term) + r'(?![a-zA-Z0-9_-])', content, re.IGNORECASE):
        _add(term, 'custom', 'config')
    ```
    Esta é a lógica anti-falso-positivo a reusar (evita "CAR" casar dentro de "scared"/"aroma"). Config em `src/mcp_memory_service/config/quality.py:74`.
  - **Domain extractors (pluggable)** — `entities.py:93-101`: itera `self._domain_extractors`, chama `ext.extract(content, metadata)`, e cada retorno é adicionado forçando `source='domain'` via `_add(ent.name, ent.entity_type, 'domain')`. Exceções são engolidas com `logging.debug`.
- **Carregamento/cache dos domain extractors:**
  - Cache module-level: `_DOMAIN_EXTRACTOR_CACHE: list | None = None` (`entities.py:36`).
  - `load_domain_extractors()` (staticmethod) — `entities.py:104`: lê env `MCP_ENTITY_EXTRACTOR_MODULES` (CSV de `module:Class` ou `module.Class`), importa, instancia, valida `isinstance(instance, DomainExtractor)`, ignora falhas com warning.
  - `get_domain_extractors()` (staticmethod) — `entities.py:145`: retorna o cache, populando na 1ª chamada (evita reimport). **Cache é global e vive pelo processo** → carregar `store_terms.json` uma vez no `__init__` do extractor é coerente.
  - Construtor: `EntityExtractor(domain_extractors=EntityExtractor.get_domain_extractors())` é o padrão usado pelos 3 callers.

**Conclusão §1:** o mecanismo plugável já entrega tudo o que precisamos. Registrar o novo extractor via `MCP_ENTITY_EXTRACTOR_MODULES=mcp_memory_service.reasoning.store_terms:StoreTermsExtractor`. O extractor lê `metadata.get('store')` para filtrar o vocabulário. Nenhuma alteração de assinatura pública é necessária.

---

## 2. Os 3 callers de `extract_entities` — o `store` está no escopo?

### Fato transversal: o objeto `Memory` NÃO tem campo `store`
- `src/mcp_memory_service/models/memory.py:39-58` — dataclass `Memory` tem `content, content_hash, tags, memory_type, metadata, embedding, created_at*...`. **Sem `store`.**
- O `store` é uma **coluna da tabela `memories`** (partição), adicionada por migração: `storage/mixins/migrations.py:327-329` (`ALTER TABLE memories ADD COLUMN store TEXT DEFAULT 'default'`) e a partição real fica no vec0 `memory_embeddings.store` (`migrations.py:290`).
- **Na escrita** o store é passado como parâmetro: `storage/mixins/store.py:83` `async def store(self, memory, skip_semantic_dedup=False, store='default')` → grava a coluna (`store.py:124,136,147-152`).
- **Na leitura o store NÃO é hidratado no `Memory`:**
  - `get_by_hash` — `storage/mixins/retrieve.py:434-436`: `SELECT content_hash, content, tags, memory_type, metadata, created_at, updated_at, created_at_iso, updated_at_iso` (9 colunas, **sem `store`**). Constrói `Memory(...)` sem store (`retrieve.py:450-460`).
  - `get_all_memories` — `retrieve.py:548-550`: SELECT idêntico + embedding (**sem `store`**); usa `store` apenas como **filtro** `WHERE m.store = ?` (`retrieve.py:560-562`).
  - `_row_to_memory` — `storage/mixins/base.py:363-386`: desempacota 9 colunas + embedding; **não lê store**.
- **Implicação:** memórias recuperadas do banco perdem a informação de store. Callers que operam sobre memórias já persistidas (graph.py action e quality/maintain) não conseguem saber o store sem mudar a query de leitura.

### Caller A — `services/memory_service.py:771` (fluxo `store_memory`, tempo de escrita)
- Chamada: `entities = extractor.extract_entities(memory.content, memory.metadata)` dentro de `_maybe_link_entities(self, memory)` — `memory_service.py:754-786`.
- **Store disponível?** No método `_maybe_link_entities` **NÃO** — ele só recebe `memory`, que não tem store.
- **MAS** o store existe no escopo do chamador: `store_memory(..., store: str = "default")` — `memory_service.py:368`. É propagado a `self.storage.store(memory, ..., store=store)` (`memory_service.py:451,492`) e `_maybe_link_entities(memory)` é chamado logo após (`memory_service.py:503`) **sem** repassar store.
- **Origem do store:** parâmetro da tool `store_memory` (default `"default"`). ✅ Disponível — só precisa ser propagado.
- **Nota:** entity linking só roda no **caminho single-memory** (`memory_service.py:503`). O caminho chunked (`memory_service.py:434-479`) NÃO chama `_maybe_link_entities` — entidades de conteúdo grande só serão extraídas depois, no `maintain` (caller C).

### Caller B — `server/handlers/graph.py:159` (tool `graph`, action `extract_entities`, sob demanda)
- Chamada: `entities = extractor.extract_entities(content, metadata)` — `graph.py:159`, sobre uma memória buscada por hash: `mem = await storage.get_by_hash(hash_val)` (`graph.py:144`).
- **Store disponível?** **NÃO** diretamente. `mem` vem de `get_by_hash` que não hidrata store (ver acima). O `arguments` da tool (`graph.py`, action `extract_entities`, ~linha 128-132) só exige `hash`; não há argumento `store` no schema atual.
- **Origem possível:** (a) adicionar arg opcional `store` à action e injetar no metadata, OU (b) fazer `get_by_hash` retornar o store (mudança de leitura) e injetar. Viável, mas exige uma das duas alterações.

### Caller C — `server/handlers/quality.py:568` (fluxo `maintain`, batch)
- Chamada: `entities = extractor.extract_entities(content, extraction_input)` — `quality.py:568`, dentro de `handle_maintain` (`quality.py:372`), iterando `_scan_slice` derivado de `_all_mems = await storage.get_all_memories()` (`quality.py:530`).
- **Store disponível?** **NÃO.** `get_all_memories()` é chamado **sem filtro de store** (varre todos os stores) e os `Memory` retornados não carregam store. `handle_maintain` recebe apenas `arguments` com `dry_run` (`quality.py:379`) — sem store.
- **Origem possível:** exige que `get_all_memories` hidrate o store por memória (mudança de leitura) OU que o maintain rode por-store (loop sobre stores conhecidos, passando `store=` ao `get_all_memories` e injetando no metadata de cada memória).

### Resumo §2
| Caller | Arquivo:linha | Store no escopo? | Origem |
|--------|---------------|------------------|--------|
| A store_memory | memory_service.py:771 (via :503, :368) | ✅ Sim | parâmetro `store` da tool |
| B graph action | graph.py:159 (via :144) | ⚠️ Não | precisa arg novo OU leitura hidratar store |
| C maintain batch | quality.py:568 (via :530) | ⚠️ Não | precisa leitura hidratar store OU loop por-store |

---

## 3. Caminho EXATO para injetar `store` no metadata (por caller)

Regra geral: como o `DomainExtractor.extract(content, metadata)` só recebe metadata, o store precisa chegar como `metadata['store']`. **Não persistir** essa chave — injetar apenas na cópia passada ao extractor (evita vazar `store` para dentro de `metadata` gravado, que já é coluna própria).

### Caller A (memory_service.py) — VIÁVEL, mínimo
- `store` já está no escopo de `store_memory` (`:368`). Propagar para `_maybe_link_entities`:
  - Mudar assinatura interna para `_maybe_link_entities(self, memory, store="default")` (método privado, não é API pública).
  - Na chamada `:503` → `await self._maybe_link_entities(memory, store=store)`.
  - Dentro do método (`:771`), montar metadata efêmero: `md = {**(memory.metadata or {}), 'store': store}` e chamar `extractor.extract_entities(memory.content, md)`.
- ✅ Zero mudança em API pública / assinatura de `extract_entities`.

### Caller B (graph.py action) — VIÁVEL com pequeno acréscimo
- Opção escolhida (mínima): ler `store` de `arguments` da action. `store = arguments.get("store", "default")` e injetar: `metadata['store'] = store` antes de `:159`.
- (O schema da tool `graph` pode ganhar um campo opcional `store`; se o cliente não enviar, cai em `"default"`.)
- Alternativa mais robusta (fora de escopo desta fase): fazer `get_by_hash` retornar o store real da linha e injetar. Requer mudar SELECT em `retrieve.py:434`. Deixar para fase posterior — nesta fase, arg explícito basta.

### Caller C (quality.py maintain) — VIÁVEL, precisa decisão
- **Opção C1 (recomendada, mínima na leitura):** fazer `get_all_memories` **também retornar o store** por memória, injetando em `metadata['store']` na hidratação. Impacto: mudar SELECT em `retrieve.py:548` (add `m.store`), e `_row_to_memory`/loop para popular `metadata['store']`. Depois no maintain (`:568`) já vem no metadata.
- **Opção C2 (sem tocar leitura):** loop por-store no maintain — para cada store conhecido (chaves do `store_terms.json` + `default`), chamar `get_all_memories(store=S)` e injetar `metadata['store']=S`. Mais chamadas, mas isolado no handler.
- Para GATE 0, registrar C1 como preferida (uma mudança de leitura serve B e C). **Decisão a validar no GREEN.**

### Viabilidade
- **A: totalmente viável, sem tocar leitura.** É o caminho crítico (extração no store_memory, que é onde o store é conhecido com certeza).
- **B e C: viáveis, mas dependem de** (i) arg novo (B) e (ii) hidratar store na leitura (C, e opcionalmente B). Nenhum é bloqueante; nenhum altera `extract_entities`.

---

## 4. Especificação do `StoreTermsExtractor(DomainExtractor)`

### Path proposto
- **Extractor:** `src/mcp_memory_service/reasoning/store_terms.py` (nova classe `StoreTermsExtractor`).
- **Dados:** `src/mcp_memory_service/data/store_terms.json` (diretório `data/` **NÃO existe** no worktree dev — criar). Formato do fork: `{ "<store>": {"locale": "...", "terms": [...]}, ... }`.
- **Registro:** env `MCP_ENTITY_EXTRACTOR_MODULES=mcp_memory_service.reasoning.store_terms:StoreTermsExtractor` (documentar em `config/quality.py` junto ao bloco de `MCP_ENTITY_CUSTOM_TERMS:74`).

### Comportamento
```python
# src/mcp_memory_service/reasoning/store_terms.py (esboço — GREEN implementa)
import json, re, logging
from pathlib import Path
from .entities import Entity  # reusa dataclass

_STORE_TERMS_PATH = Path(__file__).parent.parent / "data" / "store_terms.json"

class StoreTermsExtractor:
    """DomainExtractor: vocabulário de termos por store, lido de store_terms.json.
    Lê metadata['store'] para escolher a partição de termos. Sem store -> 'default'.
    """
    def __init__(self, path: Path | None = None):
        self._path = path or _STORE_TERMS_PATH
        self._data = self._load()               # carrega 1x (cache via get_domain_extractors)
        # pré-compila regex por termo, por store (word-boundary igual ao upstream)
        self._compiled = self._compile(self._data)

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logging.getLogger(__name__).warning(f"store_terms load failed: {e}")
            return {}

    def _compile(self, data: dict) -> dict:
        out = {}
        for store, cfg in data.items():
            terms = cfg.get("terms", []) if isinstance(cfg, dict) else (cfg or [])
            out[store] = [(t, re.compile(
                r'(?<![a-zA-Z0-9_-])' + re.escape(t) + r'(?![a-zA-Z0-9_-])',
                re.IGNORECASE)) for t in terms if t]
        return out

    def extract(self, content: str, metadata: dict | None = None) -> list[Entity]:
        md = metadata or {}
        store = md.get("store") or "default"
        rules = self._compiled.get(store, self._compiled.get("default", []))
        out = []
        for term, rx in rules:
            if rx.search(content):
                out.append(Entity(name=term, entity_type="domain_term", source="domain"))
        return out
```

### Detalhes
- **Filtro por store:** `store = metadata.get('store') or 'default'`; usa `self._compiled[store]`; fallback `default` se store desconhecido.
- **Match / anti-falso-positivo:** reusa exatamente o padrão de `entities.py:88` — `(?<![a-zA-Z0-9_-]) ... (?![a-zA-Z0-9_-])`, `re.IGNORECASE`, `re.escape(term)`. Pré-compilado no `__init__` (o extractor é cacheado por processo em `get_domain_extractors()`).
- **Retorno:** lista de `Entity(name=term, entity_type='domain_term', source='domain')`. O `source='domain'` é **redundante** porque o loop em `entities.py:97` força `source='domain'`; manter por clareza. `entity_type='domain_term'` é a escolha (poderia ser mais fino no futuro).
- **Import da dataclass:** `from .entities import Entity` (mesmo pacote `reasoning`). Cuidado com import circular: `store_terms.py` importa de `entities.py`; `entities.py` NÃO importa `store_terms.py` (é carregado dinamicamente por string) → sem ciclo.

---

## 5. Riscos e decisões

- **Metadata sem `store` (default):** `metadata.get('store') or 'default'` → usa a partição `default`. No `store_terms.json` atual, `default` tem `terms: []` → **zero termos extraídos** (comportamento seguro; sem poluição cross-store). Backward-compatible: se ninguém propaga store, nada muda.
- **Multi-word terms** (ex: `"floresta tipo B"`, `"terra indígena"`, `"Rural Environmental Registry"`): a regex word-boundary do upstream **funciona** para multi-word — os espaços internos ficam dentro do `re.escape(term)` e os lookarounds só verificam as bordas externas. Precisa de `re.IGNORECASE` (já previsto). **Risco:** variações de espaçamento/acentuação ("floresta  tipo B" com 2 espaços, ou sem acento em "terra indigena") NÃO casam. Decisão GATE 0: aceitar match literal nesta fase; normalização (NFKD/whitespace) fica para fase futura junto do locale. Anotar como limitação conhecida.
- **Locale por store:** o `store_terms.json` traz `locale` por store, mas **nesta fase o locale é ignorado** — só `terms[]` é usado. Locale afeta harvest/stopwords/normalização (spec §Locale), fora do escopo do NER agora. Não bloqueia.
- **Acentuação e `IGNORECASE`:** `re.IGNORECASE` cobre caixa, não acento. Termos com acento devem constar no JSON exatamente como aparecem no conteúdo pt-BR. OK para MIR (conteúdo controlado).
- **Performance:** regex pré-compilada por termo; store `mir` tem ~40 termos → ~40 `search` por memória. Aceitável. No `maintain` (batch, `MAINTAIN_SCAN_LIMIT=2000`) → ~80k buscas; ainda barato. Cache do extractor evita recarregar JSON.
- **Arquivo ausente:** se `store_terms.json` não existir, `_load()` retorna `{}` → extractor vira no-op silencioso. Seguro.
- **`data/` não empacotado:** confirmar no GREEN que `data/store_terms.json` entra no pacote (pyproject `package-data`/MANIFEST). Se instalado via wheel sem o JSON, path `Path(__file__).parent.parent/"data"` não resolve → no-op. Risco de empacotamento a validar.
- **Dupe entre stores:** o `_add` de `entities.py:56-60` dedupa por `name.lower()` no conjunto total de entidades daquela extração — não há colisão entre stores porque cada extração usa 1 store só.
- **Chunked path (caller A):** conteúdo grande não passa por `_maybe_link_entities` (só single). Termos só serão pegos no `maintain`. Se maintain não tiver store (§2 C), chunks grandes podem nunca ganhar domain terms. Decisão: resolver via C1 (hidratar store na leitura) para cobrir esse caso.

---

## 6. Plano de teste (GATE 3 subsequente)

Testar `StoreTermsExtractor` isoladamente (unit, sem I/O real — injetar path de fixture JSON):

1. **Match por store:** conteúdo `"F008 V07 floresta tipo B"` + `metadata={'store':'mir'}` → extrai `F008`, `V07`, `floresta tipo B` (entity_type `domain_term`, source `domain`).
2. **Isolamento entre stores:** mesmo conteúdo com `metadata={'store':'rer'}` → NÃO extrai `F008` (não está no vocabulário `rer`); extrai `CAR`/`SICAR` se presentes.
3. **Sem store = default:** `metadata={}` ou sem chave `store` → usa `default` (terms vazio) → retorna `[]`.
4. **Store desconhecido:** `metadata={'store':'inexistente'}` → fallback `default` → `[]`.
5. **Multi-word:** `"consultar floresta tipo B no mapa"` store `mir` → casa `floresta tipo B` como uma entidade única (não 3 tokens).
6. **Word-boundary anti-falso-positivo:** conteúdo `"the child was scared"` store `rer` (tem `CAR`) → `CAR` NÃO casa dentro de `scared`. Idem `"aroma"` não casa `roma`.
7. **Case-insensitive:** `"sicar"` minúsculo store `mir` → casa `SICAR`.
8. **Arquivo ausente/corrompido:** path inexistente → extractor retorna `[]` sem exceção.
9. **Integração (opcional):** via `EntityExtractor(domain_extractors=[StoreTermsExtractor(fixture)])` + `extract_entities(content, {'store':'mir'})` → entidades domain aparecem junto das de conteúdo, com `source='domain'`.
10. **Caller A e2e (integração leve):** `store_memory(content, store='mir')` → `_maybe_link_entities` deve gerar links para termos MIR (mockar graph storage).

Ferramenta: `pytest` (já usado no projeto). Fixtures: JSON temporário `tmp_path`.

---

## Plano de implementação (o que a fase GREEN fará)

**Passo 1 — Dados.** Criar `src/mcp_memory_service/data/store_terms.json` a partir do backup do fork (`git show backup/main-fork-2026-09-02:src/mcp_memory_service/data/store_terms.json`, repo `~/git/mcp-memory-service`). Formato `{store:{locale,terms[]}}`. Garantir empacotamento (pyproject package-data).

**Passo 2 — Extractor.** Criar `src/mcp_memory_service/reasoning/store_terms.py` com `StoreTermsExtractor` (ver §4): carrega+compila no `__init__`, `extract()` filtra por `metadata['store']` (fallback default), word-boundary reusado de `entities.py:88`, retorna `Entity(entity_type='domain_term', source='domain')`.

**Passo 3 — Caller A (crítico).** Em `services/memory_service.py`: mudar `_maybe_link_entities(self, memory, store="default")` (`:754`), repassar `store` na chamada (`:503`), e injetar `{**memory.metadata, 'store': store}` na chamada a `extract_entities` (`:771`).

**Passo 4 — Leitura hidrata store (serve B e C).** Em `storage/mixins/retrieve.py`: adicionar `m.store` ao SELECT de `get_all_memories` (`:548`) e `get_by_hash` (`:434`); popular `metadata['store']` na construção do Memory (ou em `_row_to_memory`, `base.py:363`). Decisão a confirmar: injetar em metadata efêmero vs. adicionar campo `store` ao Memory (preferir metadata p/ não mexer no dataclass público).

**Passo 5 — Caller B.** Em `server/handlers/graph.py` action `extract_entities`: `store = arguments.get('store','default')` (ou vindo do Passo 4) e injetar `metadata['store']` antes de `:159`.

**Passo 6 — Caller C.** Em `server/handlers/quality.py` maintain: com Passo 4, `metadata['store']` já vem por memória; garantir que o `extraction_input` (`:566`) preserve `store` além de `tags`.

**Passo 7 — Registro/config.** Documentar `MCP_ENTITY_EXTRACTOR_MODULES=mcp_memory_service.reasoning.store_terms:StoreTermsExtractor` (bloco em `config/quality.py:73-74`). Configurar env no ambiente do Claudio.

**Passo 8 — Testes (GATE 3).** Implementar casos §6.

### Arquivos criados
| Arquivo | Ação |
|---------|------|
| `src/mcp_memory_service/reasoning/store_terms.py` | novo — `StoreTermsExtractor` |
| `src/mcp_memory_service/data/store_terms.json` | novo — vocabulário per-store (do backup do fork) |
| `tests/.../test_store_terms_extractor.py` | novo — testes GATE 3 |

### Arquivos tocados
| Arquivo:linha | Mudança |
|---------------|---------|
| `services/memory_service.py:503,754,771` | propagar `store` a `_maybe_link_entities` + injetar em metadata |
| `storage/mixins/retrieve.py:434,548` | SELECT `m.store` + popular `metadata['store']` |
| `storage/mixins/base.py:363` (`_row_to_memory`) | popular `metadata['store']` (se colher via _row_to_memory) |
| `server/handlers/graph.py:159` (+schema action) | arg/injeção `store` no metadata |
| `server/handlers/quality.py:566-568` | preservar `store` no `extraction_input` |
| `config/quality.py:73-74` | doc do env de registro |
| `pyproject.toml` (package-data) | incluir `data/*.json` no pacote |

### Invariante de design
- **NÃO** alterar `EntityExtractor.extract_entities(content, metadata)` nem `DomainExtractor.extract(content, metadata)`. Todo o `store` trafega por `metadata['store']`. Backward-compatible: ausência de store ⇒ `default` ⇒ terms vazios ⇒ no-op.
