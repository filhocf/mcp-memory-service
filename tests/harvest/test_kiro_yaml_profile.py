"""Gate 3 (RED) — Fase 0 Kiro→YAML.

Testes que FALHAM antes do refactor dado→config descrito no PR atômico
'Fase 0 Kiro→YAML' do arco de ingestão. O objetivo do refactor é extrair as
constantes hardcoded de ``TranscriptParser`` (parser.py) para um YAML
declarativo ``src/mcp_memory_service/harvest/agents/kiro.yaml`` + um loader que
espelha ``harvest.patterns.load_patterns``, mantendo comportamento
BYTE-IDÊNTICO ao atual.

Estado RED esperado (motivos CERTOS, não erro de sintaxe):
  - test_loader_* / test_profile_values_* → ImportError: o módulo
    ``mcp_memory_service.harvest.agents`` e o loader ``load_agent_profile``
    ainda não existem (G4 cria).
  - test_golden_parser_exposes_profile → AttributeError/AssertionError: o
    parser ainda não expõe ``_profile`` (o refactor vai plugá-lo).
  - test_fallback_* → ImportError: o loader (e seu mecanismo de fallback) ainda
    não existe.

NUANCE DO GOLDEN (TDD):
  - ``test_golden_baseline_is_stable`` roda o parser ATUAL sobre um corpus
    sintético fixo e compara com um golden embutido. Ele PASSA hoje (baseline)
    e deve continuar passando pós-refactor (G4) — é o teste de NÃO-REGRESSÃO
    que FALHARIA se o refactor mudasse qualquer role/texto da saída. Marcado
    explicitamente abaixo como GOLDEN.
  - ``test_golden_parser_exposes_profile`` é o RED do golden: exige que o
    parser leia do profile (atributo ``_profile``). Falha hoje. Separei os dois
    para que a captura do baseline fique inequívoca e o motivo do RED seja
    isolado da comparação de saída.
"""

import json
from pathlib import Path

import pytest

from mcp_memory_service.harvest.parser import TranscriptParser


# ---------------------------------------------------------------------------
# Constantes hardcoded atuais em parser.py (fonte da verdade para equivalência)
# Mantidas aqui como espelho literal (parser.py L35-L38 + métodos L604-L628).
# ---------------------------------------------------------------------------
EXPECTED_RELEVANT_TYPES = {"user", "assistant"}
EXPECTED_KIRO_KIND_MAP = {
    "Prompt": "user",
    "Response": "assistant",
    "AssistantMessage": "assistant",
}
EXPECTED_OPENCLAW_MESSAGE_TYPES = {"prompt.submitted", "model.completed"}
EXPECTED_PAYLOAD_ROLE_MAP = {"user": "user", "assistant": "assistant"}
EXPECTED_DISCOVERY_GLOBS = [
    "*.jsonl",
    "*.trajectory.jsonl",
    "cli/*.jsonl",
    "*/*/messages.jsonl",
]
EXPECTED_INJECTED_MARKERS = [
    "<system-reminder>",
    "</system-reminder>",
    "<command-name>",
    "<command-message>",
    "<ide_opened_file>",
]
EXPECTED_SYSTEM_CUTOFF_CHARS = 10000


# ---------------------------------------------------------------------------
# Corpus sintético determinístico p/ o GOLDEN. Cobre os caminhos do parser do
# Kiro que o YAML vai parametrizar: Prompt/Response (blocos text), string
# content, toolResult, bloco injetado (filtrado por marker) e bloco acima do
# cutoff de 10k (filtrado por tamanho).
# ---------------------------------------------------------------------------
GOLDEN_KIRO_LINES = [
    {"version": "v1", "kind": "Prompt",
     "data": {"content": [{"kind": "text", "data": "Implementar a tela de login"}]},
     "timestamp": "2026-05-15T10:00:00Z", "uuid": "p1"},
    {"version": "v1", "kind": "Response",
     "data": {"content": [{"kind": "text", "data": "Vou criar o componente de login."}]},
     "timestamp": "2026-05-15T10:00:05Z", "uuid": "r1"},
    # string content (sem blocos)
    {"version": "v1", "kind": "Prompt",
     "data": {"content": "Corrigir o bug do pool de conexões"},
     "timestamp": "2026-05-15T10:01:00Z", "uuid": "p2"},
    # kind não-harvestável → descartado
    {"version": "v1", "kind": "ToolUse",
     "data": {"content": [{"kind": "text", "data": "interno, nao deve virar memoria"}]},
     "timestamp": "2026-05-15T10:01:30Z", "uuid": "x1"},
    # bloco text injetado (marker) → filtrado por _is_system_content
    {"version": "v1", "kind": "Response",
     "data": {"content": [{"kind": "text", "data": "<system-reminder>oculto</system-reminder>"}]},
     "timestamp": "2026-05-15T10:02:00Z", "uuid": "r2"},
    # bloco acima do cutoff de 10k → filtrado por tamanho
    {"version": "v1", "kind": "Response",
     "data": {"content": [{"kind": "text", "data": "x" * (EXPECTED_SYSTEM_CUTOFF_CHARS + 1)}]},
     "timestamp": "2026-05-15T10:02:30Z", "uuid": "r3"},
    # toolResult legítimo → role assistant, sem cutoff
    {"version": "v1", "kind": "Response",
     "data": {"content": [
         {"kind": "toolResult", "data": {"content": [
             {"kind": "text", "data": {"content": [{"type": "text", "text": "resultado da ferramenta"}]}}
         ]}}
     ]},
     "timestamp": "2026-05-15T10:03:00Z", "uuid": "r4"},
]

# GOLDEN embutido: saída esperada (role, texto) do parser ATUAL sobre o corpus
# acima. Qualquer divergência pós-refactor FALHA o teste de não-regressão.
GOLDEN_EXPECTED = [
    ("user", "Implementar a tela de login"),
    ("assistant", "Vou criar o componente de login."),
    ("user", "Corrigir o bug do pool de conexões"),
    ("assistant", "resultado da ferramenta"),
]


def _write_jsonl(lines, tmp_path, filename="session.jsonl"):
    path = Path(tmp_path) / filename
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    return path


# ===========================================================================
# TESTE 1 — Loader existe e carrega o perfil (RED: módulo/arquivo não existe)
# ===========================================================================
class TestLoaderExists:
    def test_load_agent_profile_importable_and_returns_dict(self):
        from mcp_memory_service.harvest.agents import load_agent_profile

        profile = load_agent_profile(agent="kiro")
        assert isinstance(profile, dict)

    def test_profile_has_expected_top_level_keys(self):
        from mcp_memory_service.harvest.agents import load_agent_profile

        profile = load_agent_profile(agent="kiro")
        # Estrutura declarativa que o G4 deve materializar no kiro.yaml.
        assert "roles" in profile
        assert "by_payload_type" in profile["roles"]
        assert "detect" in profile
        assert "discovery" in profile and "globs" in profile["discovery"]
        assert "noise" in profile
        assert "injected_markers" in profile["noise"]
        assert "system_cutoff_chars" in profile["noise"]


# ===========================================================================
# TESTE 2 — Valores do YAML == constantes hardcoded (prova de equivalência)
#            RED: profile não existe.
# ===========================================================================
class TestProfileEquivalence:
    def _profile(self):
        from mcp_memory_service.harvest.agents import load_agent_profile

        return load_agent_profile(agent="kiro")

    def test_kiro_kind_map_matches(self):
        profile = self._profile()
        assert profile["roles"]["by_kind"] == EXPECTED_KIRO_KIND_MAP

    def test_payload_role_map_matches(self):
        profile = self._profile()
        assert profile["roles"]["by_payload_type"] == EXPECTED_PAYLOAD_ROLE_MAP

    def test_relevant_types_matches(self):
        profile = self._profile()
        assert set(profile["roles"]["relevant_types"]) == EXPECTED_RELEVANT_TYPES

    def test_openclaw_message_types_matches(self):
        profile = self._profile()
        assert set(profile["detect"]["openclaw_message_types"]) == EXPECTED_OPENCLAW_MESSAGE_TYPES

    def test_discovery_globs_match(self):
        profile = self._profile()
        assert list(profile["discovery"]["globs"]) == EXPECTED_DISCOVERY_GLOBS

    def test_injected_markers_match(self):
        profile = self._profile()
        assert list(profile["noise"]["injected_markers"]) == EXPECTED_INJECTED_MARKERS

    def test_system_cutoff_matches(self):
        profile = self._profile()
        assert profile["noise"]["system_cutoff_chars"] == EXPECTED_SYSTEM_CUTOFF_CHARS


# ===========================================================================
# TESTE 3 — GOLDEN (byte-idêntico)
# ===========================================================================
class TestGolden:
    def setup_method(self):
        self.parser = TranscriptParser()

    def test_golden_baseline_is_stable(self, tmp_path):
        """GOLDEN / NÃO-REGRESSÃO.

        Passa HOJE (baseline do parser atual) e DEVE continuar passando após o
        refactor (G4). É o guardião do comportamento byte-idêntico: se o YAML
        mudar qualquer role/texto extraído, este teste quebra.
        """
        path = _write_jsonl(GOLDEN_KIRO_LINES, tmp_path)
        messages = self.parser.parse_file(path)
        actual = [(m.role, m.text) for m in messages]
        assert actual == GOLDEN_EXPECTED

    def test_golden_parser_exposes_profile(self, tmp_path):
        """RED do golden: o parser deve ler do profile declarativo.

        Hoje ``TranscriptParser`` não expõe ``_profile`` — o refactor (G4) vai
        plugar o loader e expor o perfil carregado. Falha agora por
        AttributeError/AssertionError (profile ausente), NÃO por erro de teste.
        """
        parser = TranscriptParser()
        profile = getattr(parser, "_profile", None)
        assert profile is not None, "parser ainda não expõe _profile (refactor G4 pendente)"
        # Quando existir, o profile do parser deve bater com as constantes atuais.
        assert profile["roles"]["by_kind"] == EXPECTED_KIRO_KIND_MAP
        assert profile["noise"]["system_cutoff_chars"] == EXPECTED_SYSTEM_CUTOFF_CHARS


# ===========================================================================
# TESTE 4 — Fallback (S0.6): sem kiro.yaml, cai no comportamento hardcoded
#            RED: mecanismo de fallback ainda não escrito.
# ===========================================================================
class TestFallback:
    def test_loader_falls_back_to_hardcoded_defaults(self, monkeypatch):
        """Se o kiro.yaml não existe/não carrega, o loader retorna o default
        equivalente ao hardcoded atual (compat), espelhando o fallback de
        ``load_patterns``.

        RED: o loader (e o default embutido) ainda não existem.
        """
        from mcp_memory_service.harvest import agents as agents_mod
        from mcp_memory_service.harvest.agents import load_agent_profile

        # Força 'arquivo ausente' apontando o diretório de agents p/ um tmp vazio.
        missing_dir = Path("/nonexistent-agents-dir-for-fallback-test")
        monkeypatch.setattr(agents_mod, "AGENTS_DIR", missing_dir, raising=False)

        profile = load_agent_profile(agent="kiro")
        assert profile["roles"]["by_kind"] == EXPECTED_KIRO_KIND_MAP
        assert profile["roles"]["by_payload_type"] == EXPECTED_PAYLOAD_ROLE_MAP
        assert profile["noise"]["system_cutoff_chars"] == EXPECTED_SYSTEM_CUTOFF_CHARS

    def test_parser_uses_hardcoded_when_profile_absent(self, tmp_path, monkeypatch):
        """Com o profile ausente, o parser ATUAL deve manter a saída golden.

        Hoje o parser nem consulta profile, então o parse já é o hardcoded —
        este teste ancora que o fallback NÃO deve regredir a saída. Vira RED
        quando passar a depender de um símbolo de fallback inexistente.
        """
        from mcp_memory_service.harvest import agents as agents_mod  # RED: módulo ausente

        monkeypatch.setattr(
            agents_mod, "AGENTS_DIR",
            Path("/nonexistent-agents-dir-for-fallback-test"), raising=False,
        )
        path = _write_jsonl(GOLDEN_KIRO_LINES, tmp_path)
        messages = TranscriptParser().parse_file(path)
        actual = [(m.role, m.text) for m in messages]
        assert actual == GOLDEN_EXPECTED
