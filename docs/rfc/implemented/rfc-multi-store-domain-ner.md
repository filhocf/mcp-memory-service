# Spec: Multi-store Domain NER (Entity Linking por Domínio)

**Data:** 2026-06-12
**Status:** Draft
**Relacionado:** Issue #54 (NER pipeline), #57/#62 (multi-store), DAIA

## Problema

O `MCP_ENTITY_CUSTOM_TERMS` é global — todos os termos se aplicam a todas as memórias.
Resultado: "CAR" num contexto de curadoria de vídeo gera link falso com Cadastro Ambiental Rural.

O agente que trabalha com MIR não precisa dos termos RER poluindo seu grafo de entidades,
e vice-versa. Hoje não há separação.

## Solução: Vocabulário de Entidades per-Store

Cada store tem seu próprio dicionário de termos de domínio. Entity extraction acontece
no momento do `memory_store` e usa o vocabulário do store de destino.

### Mapeamento workspace → store

| Workspace (orchestrator) | Store (memory-service) | Contexto |
|--------------------------|----------------------|----------|
| `dtp` + tag `mir-sistema` | `mir` | Meu Imóvel Rural (memórias + docs específicos) |
| `dtp` + tag `rer` | `rer` | Rural Environmental Registry |
| `dtp` + tag `roma-connect` | `mir` | Roma Connect é subsistema do MIR |
| `dtp` + tag `daia` | `daia` | Dataprev AI Assistant |
| `dtp` + tag `mcr` | `mir` | MCR/Tô em Dia = feature do MIR |
| (ingestão corporativa) | `docs-shared` | PadrãoTIC, TechDocs, Olímpia, Conexão, legislação |
| `pessoal` | `default` | Memórias pessoais, harness |
| `harness` | `default` | MCPs, steering, skills |

### Modelo de stores

```
Banco único (sqlite_vec.db):
├── partition "mir"          → memórias + docs específicos MIR
├── partition "rer"          → memórias + docs específicos RER
├── partition "daia"         → memórias + docs específicos DAIA
├── partition "docs-shared"  → PadrãoTIC, TechDocs, Olímpia, Conexão, legislação
├── partition "default"      → harness, pessoal, cross-project
└── query store="all"        → federation (busca em todas)
```

### Regra de roteamento

- Doc é de um projeto específico? → store do projeto
- Doc é corporativo/transversal? → `docs-shared`
- Memória de trabalho/decisão? → store do projeto ativo
- Não sabe? → `default`

### Como o agente sabe qual store usar

1. **Hook de sessão** (startup-hook): identifica workspace ativo → define `ACTIVE_STORE`
2. **Steering work-management.md**: ao avançar item no orchestrator, tag do item → store
3. **Explícito**: usuário diz "store docs" ou sistema infere do diretório (`~/git/mir/` → mir)
4. **Default**: se nenhum contexto → `store="default"` (backward compat)

### Vocabulário per-Store

```json
{
  "mir": [
    "F001", "F002", "F003", "F004", "F005", "F008", "F013", "F014", "F020", "F022",
    "V07", "V08",
    "SICAR", "SNCR", "SIGEF", "CAF", "CAR",
    "floresta tipo B", "floresta pública",
    "terra indígena", "TI",
    "terra quilombola", "TQ",
    "unidade de conservação", "UC",
    "embargo", "IBAMA",
    "PRODES", "desmatamento",
    "trabalho escravo", "lista suja",
    "Tô em Dia", "regularidade",
    "Roma Connect", "WSO2", "gateway",
    "Spring Boot", "WebFlux", "PostGIS",
    "Produção Certa", "ZARC"
  ],
  "rer": [
    "CAR", "SICAR", "DPG",
    "geoserver", "calc_engine", "core",
    "install.sh", "docker compose",
    "Rural Environmental Registry",
    "Kubernetes", "ghcr.io"
  ],
  "mcr": [
    "MCR", "Tô em Dia", "regularidade",
    "BCB", "Banco Central",
    "crédito rural", "PRONAF", "PRONAMP",
    "impedimento", "restrição",
    "painel regularidade",
    "DataLake", "Kafka", "Analytics"
  ],
  "daia": [
    "DAIA", "AI Assistant",
    "Ollama", "ModelArts",
    "pipeline", "enforcement",
    "anomaly detection", "policy",
    "PadrãoTIC", "TechDocs", "Olímpia"
  ],
  "roma-connect": [
    "Roma Connect", "HCSO", "Huawei Cloud",
    "API Group", "backend", "datasource",
    "custom backend", "bind domínio",
    "certificado SSL", "subscription"
  ],
  "default": []
}
```

### Implementação (fork local)

**Onde:** `src/mcp_memory_service/config/entities.py` (novo arquivo)

```python
import json
from pathlib import Path

STORE_TERMS_PATH = Path(__file__).parent.parent / "data" / "store_terms.json"

def get_store_terms(store: str = "default") -> list[str]:
    """Load entity terms for a specific store."""
    if not STORE_TERMS_PATH.exists():
        return []
    data = json.loads(STORE_TERMS_PATH.read_text())
    return data.get(store, data.get("default", []))
```

**Integração no entity extractor:**
1. No momento do `memory_store(content, store="mir")`, o extractor carrega `get_store_terms("mir")`
2. Faz lookup case-insensitive dos termos no conteúdo
3. Cada match → `store_entity_link(content_hash, term, "domain_term")`

**Integração no steering:**
- `work-management.md`: quando item tem tag `mir-sistema`, chamadas memory passam `store="mir"`
- `startup-hook.md`: workspace → ACTIVE_STORE no contexto da sessão

## Impacto Esperado

Cenário "Tô em Dia" com store `mir`:
- Memória: "F008 V07 — query floresta tipo B com ST_Intersects"
- Entidades extraídas: `F008`, `V07`, `floresta tipo B`
- `memory_explore("regularidade imóvel")` → encontra TODAS as verificações vinculadas

Sem store terms: nenhuma dessas entidades seria extraída (não tem @ nem #).

## Sequenciamento

1. **Agora (local):** configurar `store_terms.json` + integrar no entity extractor do fork
2. **Pós-v11:** propor ao upstream como implementação do #54 (NER plugável = store_terms como "plugin zero")
3. **DAIA:** cada cliente teria seu store_terms.json — self-service

## Relação com upstream

- `MCP_ENTITY_CUSTOM_TERMS` (env var global) = versão flat do mesmo conceito
- #54 (NER plugável) = versão extensível (hooks, modelos, API)
- Esta spec = meio-termo pragmático (JSON per-store, sem modelo ML)

## Locale per-Store

Cada store pode ter um locale associado que afeta:
1. **Entity extraction** — patterns de capitalização, stopwords, composição de termos
2. **Harvest meta-filter** — keywords de rejeição (pt_BR.yaml, en.yaml, de.yaml)
3. **Normalização** — NFKD + transliteração específica por idioma

### Mapeamento store → locale

| Store | Locale | Motivo |
|-------|--------|--------|
| `mir` | `pt_BR` | Sistema gov.br, toda documentação em português |
| `rer` | `en` | Projeto DPG internacional, docs em inglês |
| `mcr` | `pt_BR` | Legislação BCB, português |
| `daia` | `pt_BR` | Dataprev, português |
| `roma-connect` | `pt_BR,en` | Docs Huawei em inglês, uso interno em português |
| `default` | `pt_BR,en` | Multilíngue (sessões misturam idiomas) |

### Config

```json
{
  "mir": {
    "locale": "pt_BR",
    "terms": ["F008", "floresta tipo B", "terra indígena", ...]
  },
  "rer": {
    "locale": "en",
    "terms": ["CAR", "geoserver", "calc_engine", ...]
  },
  "default": {
    "locale": "pt_BR,en",
    "terms": []
  }
}
```

### Impacto do locale no pipeline

1. **Entity extraction**: termos compostos em pt-BR ("floresta pública tipo B") exigem lookup multi-word. Em inglês, capitalização já ajuda ("Rural Environmental Registry").
2. **Harvest filter**: `HARVEST_LOCALE` hoje é global. Com per-store, ao harvester processar uma sessão com tag `mir`, carrega `pt_BR.yaml` automaticamente.
3. **Search**: stop-words por locale (não ranquear "de", "da", "para" como tokens significativos em pt-BR).
4. **Futuro**: quando NER ML chegar (#54), o modelo carregado depende do locale (spaCy pt_core_news, en_core_web, etc).
