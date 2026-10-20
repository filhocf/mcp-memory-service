#!/usr/bin/env python3
"""Injeta a identidade do agente nas gravações do mms.

O mms resolve `agent_id` nesta ordem: argumento da chamada -> variável
MCP_AGENT_ID do *servidor* -> vazio. Como o servidor é compartilhado, definir
a variável lá carimbaria todos os clientes com o mesmo nome (foi o que
produziu `agent_id: "zero"` nas minhas gravações). A identidade é do cliente,
então ela entra aqui: este hook reescreve os argumentos da chamada.

Contrato do Hermes: pre_tool_call aceita {"action": "modify", "args": {...}}
(shell_hooks._parse_pre_tool_call). Silêncio = nenhuma mudança.
"""

from __future__ import annotations

import json
import sys

AGENTE = os.environ.get("MCP_AGENT_ID", "")

# Ferramentas do mms que registram autoria. `memory_update` fica de fora de
# propósito: ele altera metadata existente e não deve reescrever dono.
FERRAMENTAS = {
    "memory_store",
    "memory_store_session",
    "mistake_note_add",
}


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    if dados.get("hook_event_name") != "pre_tool_call":
        return 0

    nome = str(dados.get("tool_name") or "")
    curto = nome.split("__")[-1]
    if curto not in FERRAMENTAS:
        return 0

    args = dados.get("args")
    if not isinstance(args, dict):
        return 0

    novo = dict(args)
    mudou = False

    if not novo.get("agent_id"):
        novo["agent_id"] = AGENTE
        mudou = True

    sessao = dados.get("session_id")
    if sessao and not novo.get("conversation_id"):
        novo["conversation_id"] = str(sessao)
        mudou = True

    if not mudou:
        return 0

    json.dump({"action": "modify", "args": novo}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
