#!/usr/bin/env python3
"""Hook pre_llm_call: injeta mensagens não lidas de outros agentes (A3 sobre mms).

Regra da RFC inter-agent-inbox: a decisão de entregar é do servidor/runtime, não da
disciplina do agente. Este hook roda a cada turno, é fail-open e tem teto de tempo.
"""
import json
import subprocess
import sys
import socket

PY = "/home/claudio/git/mcp-memory-service/.venv/bin/python"
SCRIPT = "/home/claudio/git/mms-lab-precisao/scripts/a3_inbox.py"

try:
    out = subprocess.run(
        [PY, SCRIPT, "hook", "--agent", "tpol", "--host", socket.gethostname()],
        capture_output=True, text=True, timeout=6,
    )
    saida = out.stdout.strip()
    if saida:
        print(saida)
except Exception:
    pass
sys.exit(0)
