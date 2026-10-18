"""Experimento: chunking por tokens (≤128) recupera o recall perdido pelo truncamento?

Contexto medido (diário de gate / spec de precisão):
  * O tokenizer do modelo embutia cada memória com truncamento em 128 tokens,
    então ~53,6% do texto do acervo nunca virou vetor.
  * Baseline SEM chunking: Recall@10 = 0,200 pelo caminho do serviço (sqlite-vec
    + FTS + 4 modos); 0,000 no cosseno puro (harness ``model_ab`` a max_len=128).

Este experimento isola a variável "chunking" no mesmo harness de cosseno puro:
  * **sem_chunking**  — 1 "chunk" por memória = texto inteiro, embutido com
    ``max_len=128`` (o modelo só vê os 128 primeiros tokens → reproduz o
    truncamento do serviço).
  * **com_chunking**  — cada memória é cortada em janelas de ≤ ``max_tokens``
    tokens (com ``overlap``); cada janela vira um vetor. Assim 100% do texto é
    vetorizado.

Acerto (ambos os modos): QUALQUER chunk cujo ``content_hash`` do pai pertence a
``case["gold_hashes"]`` aparece no top-k por similaridade de cosseno. MRR usa a
posição (1-based) do primeiro acerto no top-k.

A comparação é "apples-to-apples": os dois modos usam o MESMO ``max_len`` no
embed; a única diferença é o texto longo é ou não dividido antes de embutir.

Uso (a partir da raiz do worktree):

  PYTHONPATH=$PWD/src /home/claudio/git/mcp-memory-service/.venv/bin/python \
    -m eval.chunking_experiment \
    --db /path/snapshot.db \
    --cases eval/recall_cases.json \
    --model /home/claudio/.cache/mcp_memory/onnx_models/paraphrase-multilingual-MiniLM-L12-v2 \
    --max-tokens 128 --overlap 32 --limit 2000 \
    --out /tmp/chunking_amostra.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

#: Reuse do harness de A/B de modelos (independente do storage): embedding com
#: mean-pooling+L2 (idêntico ao loader ONNX do serviço), busca por cosseno, e
#: validação do dataset.
from scripts.benchmarks.model_ab import (
    _build_tokenizer,
    embed_texts,
    load_cases,
    topk_positions,
)

#: URI SQLite somente-leitura (R6 — nenhuma escrita possível).
_RO_URI = "file:{path}?mode=ro"

#: SQL do corpus: memórias vivas de conteúdo não vazio, ordem determinística.
#: (mesmo recorte de ``model_ab.load_corpus`` / do retrieve do serviço)
_CORPUS_SQL = (
    "SELECT content_hash, content FROM memories "
    "WHERE deleted_at IS NULL AND content IS NOT NULL "
    "AND LENGTH(TRIM(content)) > 0 "
    "ORDER BY rowid"
)


# ---------------------------------------------------------------------------
# 1. Chunking por janelas de tokens
# ---------------------------------------------------------------------------


def chunk_por_tokens(
    texto: str,
    tokenizer,
    max_tokens: int = 128,
    overlap: int = 32,
) -> list[str]:
    """Corta ``texto`` em janelas de até ``max_tokens`` tokens e devolve o texto
    decodificado de cada janela.

    * Texto com ≤ ``max_tokens`` tokens → uma única janela (o texto inteiro).
    * Janelas deslizam com passo ``max_tokens - overlap`` (com ``overlap``=0,
      janelas contíguas e sem recorte). ``overlap`` limitado a ``< max_tokens``.
    * Cada janela é decodificada com ``tokenizer.decode`` (a spec exige decode).

    Retorna ``[]`` para texto vazio. A ordenação é preservada (janela 0 =
    começo do texto).
    """
    if not texto or not texto.strip():
        return []
    if hasattr(tokenizer, "no_truncation"):
        tokenizer.no_truncation()

    max_tokens = max(1, int(max_tokens))
    overlap = max(0, int(overlap))
    if overlap >= max_tokens:
        overlap = max_tokens - 1
    step = max(1, max_tokens - overlap)

    ids = list(tokenizer.encode(texto).ids)
    n = len(ids)
    if n == 0:
        return []
    if n <= max_tokens:
        # uma janela = o texto inteiro (decodificado p/ consistência)
        dec = tokenizer.decode(ids)
        return [dec] if dec and dec.strip() else []

    chunks: list[str] = []
    start = 0
    while start < n:
        end = min(start + max_tokens, n)
        dec = tokenizer.decode(ids[start:end])
        if dec and dec.strip():
            chunks.append(dec)
        if end == n:
            break
        start += step
    return chunks


# ---------------------------------------------------------------------------
# 2. Carregamento do corpus já em chunks
# ---------------------------------------------------------------------------


def _read_corpus_rows(
    db_path: str, store: str | None = "default", limit: int | None = None
) -> list[tuple[str, str]]:
    """Memórias vivas de conteúdo não vazio como ``[(content_hash, content)]``.

    Abre em ``mode=ro`` (R6). ``limit`` recorta as primeiras ``limit`` memórias
    por ``rowid`` (para teste rápido); ``store=None`` usa o acervo inteiro.
    """
    sql = _CORPUS_SQL
    params: tuple = ()
    if store is not None:
        sql = sql.replace("ORDER BY rowid", "AND store = ? ORDER BY rowid")
        params = (store,)
    if limit is not None:
        sql = sql + " LIMIT ?"
        params = params + (int(limit),)
    conn = sqlite3.connect(_RO_URI.format(path=db_path), uri=True)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [(str(h), str(c)) for h, c in rows]


def load_corpus_chunks(
    db_path: str,
    store: str | None = "default",
    tokenizer=None,
    max_tokens: int = 128,
    overlap: int = 32,
    limit: int | None = None,
) -> list[tuple[str, str]]:
    """Corpus como ``[(content_hash_pai, chunk_texto)]``.

    * ``tokenizer=None`` → SEM chunking: cada memória vira 1 "chunk" = texto
      inteiro (o embedding depois trunca em ``max_len`` → regime do serviço).
    * ``tokenizer`` fornecido → cada memória é cortada em janelas via
      :func:`chunk_por_tokens` (100% do texto vetorizado).

    O índice no vetor de embeddings casa com a ordem desta lista (usada p/
    mapear chunk → ``content_hash`` do pai).
    """
    rows = _read_corpus_rows(db_path, store, limit)
    out: list[tuple[str, str]] = []
    for h, content in rows:
        if tokenizer is None:
            out.append((h, content))
        else:
            for c in chunk_por_tokens(content, tokenizer, max_tokens, overlap):
                out.append((h, c))
    return out


# ---------------------------------------------------------------------------
# 3. Avaliação: recall@k / mrr@k com e sem chunking
# ---------------------------------------------------------------------------


def _metrics_from_positions(
    positions: dict[str, list[int]],
    chunk_parent_hashes: list[str],
    cases: list[dict],
    k: int,
) -> dict:
    """Agrega recall@k / mrr@k.

    ``positions[case_id]`` = índices de chunk (em ordem de rank). Acerto = o
    primeiro índice cujo pai (``chunk_parent_hashes[idx]``) pertence a
    ``case["gold_hashes"]``; posição 1-based, acerto além do top-k é miss.
    """
    k = int(k)
    parent = list(chunk_parent_hashes)
    casos: dict[str, int | None] = {}
    recalls: list[float] = []
    reciprocals: list[float] = []
    for case in sorted(cases, key=lambda c: str(c.get("id"))):
        case_id = str(case.get("id"))
        gold = {str(h) for h in (case.get("gold_hashes") or [])}
        ranked = (positions.get(case_id) or [])[:k]
        pos: int | None = None
        if gold:
            for rank, idx in enumerate(ranked, start=1):
                if parent[idx] in gold:
                    pos = rank
                    break
        casos[case_id] = pos
        if pos is not None and pos <= k:
            recalls.append(1.0)
            reciprocals.append(1.0 / pos)
        else:
            recalls.append(0.0)
            reciprocals.append(0.0)
    n = len(cases)
    return {
        f"recall@{k}": (sum(recalls) / n) if n else 0.0,
        f"mrr@{k}": (sum(reciprocals) / n) if n else 0.0,
        "casos": casos,
    }


def avaliar(
    db_path: str,
    casos: list[dict],
    onnx_dir: str,
    max_tokens: int = 128,
    overlap: int = 32,
    k: int = 10,
    *,
    chunking: bool = True,
    limit: int | None = None,
    store: str | None = "default",
    max_len: int = 128,
) -> dict:
    """Embute chunks (ou memórias) e queries, busca top-k por cosseno, e mede.

    * ``chunking=True``  → cada memória em janelas de ≤ ``max_tokens`` (c/ overlap).
    * ``chunking=False`` → 1 "chunk" por memória (texto inteiro), embutido com
      ``max_len`` (truncamento do serviço).

    Ambos usam ``max_len`` no embed (padrão 128 = regime do modelo). Acerto =
    QUALQUER chunk do ``gold_hash`` no top-k. Retorna recall@k, mrr@k, posições
    por caso, contagens e tempos.
    """
    t0 = time.perf_counter()
    store = None if store == "all" else store

    tokenizer = _build_tokenizer(onnx_dir) if chunking else None
    corpus = load_corpus_chunks(
        db_path, store, tokenizer, max_tokens, overlap, limit
    )
    if not corpus:
        raise ValueError("corpus vazio — snapshot sem memórias vivas?")

    chunk_parent = [h for h, _ in corpus]
    chunk_texts = [c for _, c in corpus]
    queries = [case["pergunta"] for case in casos]

    t = time.perf_counter()
    corpus_emb = embed_texts(onnx_dir, chunk_texts, batch=64, max_len=max_len)
    corpus_ms = time.perf_counter() - t

    t = time.perf_counter()
    query_emb = embed_texts(onnx_dir, queries, batch=16, max_len=max_len)
    query_ms = time.perf_counter() - t

    dim = int(corpus_emb.shape[1]) if corpus_emb.size else 0

    positions: dict[str, list[int]] = {}
    for i, case in enumerate(casos):
        positions[str(case["id"])] = topk_positions(corpus_emb, query_emb[i], k)

    metrics = _metrics_from_positions(positions, chunk_parent, casos, k)

    n_memorias = (
        len({h for h, _ in corpus}) if chunking else len(corpus)
    )

    entry = {
        "mode": "com_chunking" if chunking else "sem_chunking",
        "max_tokens": int(max_tokens),
        "overlap": int(overlap),
        "max_len": int(max_len),
        "k": int(k),
        "limit": limit,
        "n_memorias": n_memorias,
        "n_chunks": len(corpus),
        "dim": dim,
        "corpus_embed_s": round(corpus_ms, 3),
        "query_embed_s": round(query_ms, 3),
        "total_s": round(time.perf_counter() - t0, 3),
    }
    entry.update(metrics)
    return entry


# ---------------------------------------------------------------------------
# 4. CLI
# ---------------------------------------------------------------------------


def _run(
    db: str,
    casos: list[dict],
    model: str,
    max_tokens: int,
    overlap: int,
    k: int,
    limit: int | None,
    store: str,
    max_len: int,
    only: str,
) -> dict:
    """Roda o(s) modo(s) pedidos e monta o relatório comparativo."""
    results: dict[str, dict] = {}
    if only in ("both", "none"):
        results["sem_chunking"] = avaliar(
            db, casos, model, max_tokens, overlap, k,
            chunking=False, limit=limit, store=store, max_len=max_len,
        )
    if only in ("both", "chunking"):
        results["com_chunking"] = avaliar(
            db, casos, model, max_tokens, overlap, k,
            chunking=True, limit=limit, store=store, max_len=max_len,
        )
    return results


def _print_table(results: dict[str, dict], k: int) -> None:
    rk, mk = f"recall@{k}", f"mrr@{k}"
    header = (
        f"{'modo':<14} {'mem':>6} {'chunks':>8} {rk:>10} {mk:>9} "
        f"{'embed_s':>9} {'total_s':>9}"
    )
    print("\n" + header, file=sys.stderr)
    print("-" * len(header), file=sys.stderr)
    for name in ("sem_chunking", "com_chunking"):
        if name not in results:
            continue
        r = results[name]
        print(
            f"{name:<14} {r['n_memorias']:>6} {r['n_chunks']:>8} "
            f"{r[rk]:>10.3f} {r[mk]:>9.3f} "
            f"{r['corpus_embed_s']:>9.1f} {r['total_s']:>9.2f}",
            file=sys.stderr,
        )
    if "sem_chunking" in results and "com_chunking" in results:
        d_recall = results["com_chunking"][rk] - results["sem_chunking"][rk]
        d_mrr = results["com_chunking"][mk] - results["sem_chunking"][mk]
        print(
            f"\nΔ chunking: recall@{k} {d_recall:+.3f}  mrr@{k} {d_mrr:+.3f}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="chunking_experiment",
        description=(
            "Prova/refuta que chunking por tokens (≤128) recupera o recall@k "
            "perdido pelo truncamento — no mesmo harness de cosseno puro "
            "(sem_chunking vs com_chunking)."
        ),
    )
    p.add_argument("--db", required=True, help="snapshot SQLite (read-only)")
    p.add_argument(
        "--cases", default="eval/recall_cases.json",
        help="dataset de casos (padrão eval/recall_cases.json)",
    )
    p.add_argument(
        "--model", required=True,
        help="diretório do modelo ONNX (com onnx/model.onnx e tokenizer.json)",
    )
    p.add_argument("--max-tokens", type=int, default=128,
                   help="tamanho da janela em tokens (padrão 128)")
    p.add_argument("--overlap", type=int, default=32,
                   help="overlap em tokens entre janelas (padrão 32)")
    p.add_argument("--k", type=int, default=10, help="top-k (padrão 10)")
    p.add_argument("--max-len", type=int, default=128,
                   help="tokens máximos no embed (padrão 128 = regime do modelo)")
    p.add_argument("--limit", type=int, default=None,
                   help="limita nº de memórias (teste rápido; None = corpus inteiro)")
    p.add_argument("--store", default="default",
                   help="partição de memória (padrão 'default'; 'all' = acervo inteiro)")
    p.add_argument("--only", default="both", choices=["both", "chunking", "none"],
                   help="modo(s) a rodar (padrão both = compara sem vs com chunking)")
    p.add_argument("--out", default=None, help="grava o relatório JSON neste arquivo")
    args = p.parse_args(argv)

    if not os.path.isfile(args.db):
        print(f"erro: snapshot não encontrado em {args.db!r}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.model):
        print(f"erro: modelo não encontrado em {args.model!r}", file=sys.stderr)
        return 2

    try:
        casos = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"erro: dataset inválido: {exc}", file=sys.stderr)
        return 2

    try:
        results = _run(
            args.db, casos, args.model, args.max_tokens, args.overlap,
            args.k, args.limit, args.store, args.max_len, args.only,
        )
    except Exception as exc:  # noqa: BLE001 - reporta e sai com erro
        print(f"erro: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    report = {
        "meta": {
            "db": args.db,
            "cases": args.cases,
            "model": args.model,
            "max_tokens": args.max_tokens,
            "overlap": args.overlap,
            "max_len": args.max_len,
            "k": args.k,
            "limit": args.limit,
            "store": args.store,
            "n_cases": len(casos),
        },
        "results": results,
    }
    payload = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)
    _print_table(results, args.k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
