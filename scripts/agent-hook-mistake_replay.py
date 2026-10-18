#!/usr/bin/env python3
"""Hook pre_llm_call: replay de erros conhecidos (mistake notes) por gatilho do runtime.

A skill manda buscar padrões de erro no início da tarefa; disciplina falha, então o
gatilho passa a ser o runtime. Lê o `user_message` do payload do hook, busca notas de
erro semelhantes e injeta no máximo duas, com similaridade acima do limiar.

Nota de campo: `mistake_note_search` do mms devolve vazio mesmo quando a nota existe
(verificado em 18/out: `memory_search` acha, `memory_type="mistake"` filtra, o tool
dedicado não). Por isso aqui usamos `memory_search` com filtro de tipo.

Fail-open: qualquer erro → não injeta nada e sai com 0.
"""
import json
import os
import sys
import urllib.request

PORT = 3202
LIMIAR = 0.55
MAXIMO = 2


def buscar(user_message: str) -> list[dict]:
    """Match lexical direto no SQLite.

    Motivo: `mistake_note_search` devolve vazio mesmo havendo nota, e o filtro
    `memory_type` do `memory_search` é ignorado (devolve qualquer tipo). Com 295
    notas o custo de varrer tudo é ~10 ms e a precisão lexical é melhor que a
    semântica — é o quadrante "corpus pequeno e textual" da análise do CdIA.
    """
    import re
    import sqlite3

    db = os.path.expanduser(os.environ.get("A3_DB", "~/local-data/mcp/sqlite_vec.db"))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    try:
        rows = con.execute(
            "SELECT content FROM memories WHERE memory_type = 'mistake' AND deleted_at IS NULL"
        ).fetchall()
    finally:
        con.close()

    def toks(t: str) -> set[str]:
        return {w for w in re.findall(r"[a-zà-ú0-9_]{4,}", t.lower())}

    alvo = toks(user_message)
    if not alvo:
        return []
    pontuadas = []
    for (content,) in rows:
        if not content:
            continue
        peso = len(alvo & toks(content))
        if peso:
            pontuadas.append((peso, content))
    pontuadas.sort(key=lambda x: -x[0])
    saida = []
    for peso, content in pontuadas[:MAXIMO]:
        if peso < 3 or peso / max(len(alvo), 1) < 0.12:
            break
        saida.append({"texto": " ".join(content.split())[:280]})
    return saida


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    msg = (payload.get("user_message") or "").strip()
    if len(msg) < 8:
        return 0
    try:
        notas = buscar(msg)
    except Exception:
        return 0
    if not notas:
        return 0
    linhas = ["[ERROS CONHECIDOS — não repetir]"]
    linhas += [f"- {n['texto']}" for n in notas]
    print(json.dumps({"context": "\n".join(linhas)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
