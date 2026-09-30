# Spec: Kiro CLI Headless como LLM Provider

**Data:** 2026-06-12
**Status:** Draft
**Relacionado:** multi-provider harvest/rewriter, fact-extraction-spec, OP-9

## Problema

O pipeline LLM do mcp-memory-service (harvest classifier, distill rewriter, fact extraction) depende de APIs externas:
- DeepSeek → pago por token, rate limit
- Groq → free tier limitado, instável
- Ollama → local mas modelos pequenos (4B-14B)

Resultado: custo acumulado, dependência de terceiros, modelos limitados.

## Solução: Kiro CLI como Provider LLM

O Kiro CLI headless (`--no-interactive` + `KIRO_API_KEY`) dá acesso a modelos potentes (Sonnet 4, Haiku) **sem custo adicional** (incluído na subscription).

### Interface

```python
class KiroHeadlessProvider:
    """LLM provider via Kiro CLI headless mode."""
    
    def __init__(self, model: str = "auto", timeout: int = 60):
        self.model = model  # auto, sonnet, haiku
        self.timeout = timeout
    
    async def complete(self, prompt: str, system: str = "") -> str:
        """Run Kiro CLI headless and return response."""
        cmd = [
            "kiro-cli", "--no-interactive",
            "--model", self.model,
            "--print-only",  # output only the response
        ]
        if system:
            cmd.extend(["--system", system])
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=self.timeout
        )
        return stdout.decode().strip()
```

### Integração no Multi-Provider

```python
# harvest/rewriter.py — provider chain
PROVIDERS = [
    KiroHeadlessProvider(model="haiku"),   # $0, rápido, bom para classificação
    DeepSeekProvider(),                     # fallback barato
    GroqProvider(),                         # fallback rápido  
    OllamaProvider(model="qwen2.5:14b"),  # fallback offline
]
```

### Modelo por Tarefa

| Tarefa | Modelo Kiro | Motivo |
|--------|-------------|--------|
| Harvest classifier | Haiku | Rápido, decisão simples (sim/não + tipo) |
| Distill rewriter | Sonnet | Qualidade de escrita, reformulação |
| Fact extraction | Sonnet | Compreensão de texto, extração estruturada |
| Entity NER (futuro) | Haiku | Pattern matching rápido |

### Flags CLI Necessárias

Verificar na doc oficial quais flags existem:
- `--no-interactive` → não espera input do terminal ✅ (confirmado)
- `--print-only` ou equivalente → só output sem chrome da TUI ❓ (verificar)
- `--model` → selecionar modelo ❓ (verificar se existe)
- `--system` → system prompt ❓ (verificar)
- stdin como input → prompt via pipe ❓ (verificar)

**Pesquisa necessária:** testar `kiro-cli --help` para flags disponíveis no headless mode.

### Vantagens

| Aspecto | Kiro Headless | DeepSeek API | Groq | Ollama |
|---------|:------------:|:------------:|:----:|:------:|
| Custo | $0 | ~$0.01/call | Free tier | $0 |
| Modelo | Sonnet 4 / Haiku | DeepSeek V3 | Llama 3.3 70B | Qwen 14B |
| Qualidade | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Latência | ~3-5s (CLI spawn) | ~1-2s | ~0.5s | ~2-10s |
| Rate limit | Subscription cap | Token-based | 30 req/min | ∞ |
| Disponibilidade | 99%+ | 95% | 90% | 100% (local) |

### Desvantagens / Riscos

1. **Latência de spawn** — cada call inicia um processo CLI (~2-3s overhead)
   - Mitigação: batch prompts, não chamar para tarefas triviais
2. **Parsing output** — TUI pode adicionar decoração
   - Mitigação: `--print-only` ou regex para extrair resposta limpa
3. **Rate limit subscription** — Kiro pode ter cap de requests/dia
   - Mitigação: usar como first-choice, fallback para DeepSeek se throttled
4. **Dependência de KIRO_API_KEY** — precisa estar configurado
   - Mitigação: fallback automático se key não disponível

### Verificação Prévia (antes de implementar)

```bash
# 1. Testar se headless funciona
echo "Responda apenas: OK" | kiro-cli --no-interactive 2>/dev/null

# 2. Listar flags disponíveis
kiro-cli --help | grep -i "model\|print\|system\|interactive"

# 3. Verificar KIRO_API_KEY
echo $KIRO_API_KEY | head -c5
```

## Sequenciamento

1. Spec (este documento) ✅
2. Verificar flags reais do Kiro CLI headless (teste manual)
3. Implementar `KiroHeadlessProvider` com interface compatível com providers existentes
4. Integrar como first-choice no multi-provider chain
5. Testar com fact-extraction (tarefa real)

## Relação com Upstream

- Upstream usa `GROQ_API_KEY` hardcoded no classifier
- Nossa contribuição futura: propor interface `LLMProvider` genérica (plugável)
- Kiro headless seria um provider específico nosso (não faz sentido upstream — eles não usam Kiro)
