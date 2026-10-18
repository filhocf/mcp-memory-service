"""Experimento A/B de modelos de embedding — INDEPENDENTE do storage.

Motivação (diário de gate / spec de precisão): o ``recall_harness`` mede a busca
do serviço (sqlite-vec + 4 modos). Para comparar **modelos** de embedding de
forma isolada, este harness embute o corpus e as queries com cada modelo ONNX
local e mede recall@k / mrr@k por similaridade de cosseno — sem tocar no
sqlite-vec nem no storage.

Decisões:
  * Corpus: memórias vivas (``deleted_at IS NULL``) de conteúdo não vazio, lidas
    do snapshot em ``mode=ro`` (R6 — nenhuma escrita possível).
  * Gabarito: ``gold_hashes`` de ``eval/recall_cases.json`` (a memória que
    responde ao caso). Acerto = ``gold_hash`` presente no top-k por cosseno.
    (Difere do harness de serviço, que casa ``gold_terms`` por substring no
    conteúdo — por isso os números podem divergir do baseline 20%.)
  * Pooling: mean pooling com attention mask + normalização L2 (idêntico ao
    loader ONNX do serviço).
  * Prefixos: modelos ``multilingual-e5-*`` exigem ``"query: "`` nas queries e
    ``"passage: "`` nos documentos. Configurável via ``--model ...,prefixo=Q/P``.

Uso (CLI, a partir da raiz do worktree):

  PYTHONPATH=$PWD/src python -m scripts.benchmarks.model_ab \
    --db /path/snapshot.db \
    --model atual=/path/a/dir \
    --model granite=/path/b/dir \
    --model e5-small=/path/c/dir,prefixo=query/passage \
    --out /tmp/model_ab.json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

import numpy as np

#: Prefixo URI SQLite para conexões somente-leitura (R6).
_RO_URI = "file:{path}?mode=ro"

#: SQL do corpus: memórias vivas de conteúdo não vazio, ordem determinística.
_CORPUS_SQL = (
    "SELECT content_hash, content FROM memories "
    "WHERE deleted_at IS NULL AND content IS NOT NULL "
    "AND LENGTH(TRIM(content)) > 0 "
    "ORDER BY rowid"
)

# Imports pesados sob guard: os testes de unidade monkeypatcham
# ``_build_session``/``_build_tokenizer`` e nunca carregam os ONNX reais.
try:  # pragma: no cover - depende do ambiente
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    ort = None
    ONNX_AVAILABLE = False

try:  # pragma: no cover - depende do ambiente
    from tokenizers import Tokenizer
    TOKENIZERS_AVAILABLE = True
except ImportError:  # pragma: no cover
    Tokenizer = None
    TOKENIZERS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Carregamento do modelo / tokenizer (fáceis de mockar nos testes)
# ---------------------------------------------------------------------------


def _resolve_onnx(onnx_dir: str) -> str:
    """Caminho do ``.onnx``: prefere ``onnx/model.onnx``, senão na raiz."""
    d = str(onnx_dir)
    for cand in (os.path.join(d, "onnx", "model.onnx"), os.path.join(d, "model.onnx")):
        if os.path.isfile(cand):
            return cand
    # fallback: o primeiro .onnx (ordenado) em onnx/ ou na raiz
    for sub in ("onnx", ""):
        base = os.path.join(d, sub) if sub else d
        if os.path.isdir(base):
            for fn in sorted(os.listdir(base)):
                if fn.endswith(".onnx"):
                    return os.path.join(base, fn)
    raise FileNotFoundError(f"nenhum .onnx em {onnx_dir!r} (busquei onnx/ e raiz)")


def _build_session(onnx_dir: str):
    """Sessão onnxruntime (CPU) para o modelo em ``onnx_dir``."""
    if not ONNX_AVAILABLE:
        raise ImportError("onnxruntime não está instalado")
    return ort.InferenceSession(_resolve_onnx(onnx_dir), providers=["CPUExecutionProvider"])


def _build_tokenizer(onnx_dir: str):
    """Tokenizer (tokenizers.Tokenizer) a partir de ``onnx_dir/tokenizer.json``."""
    if not TOKENIZERS_AVAILABLE:
        raise ImportError("tokenizers não está instalado")
    tok_path = os.path.join(str(onnx_dir), "tokenizer.json")
    if not os.path.isfile(tok_path):
        raise FileNotFoundError(f"tokenizer.json não encontrado em {onnx_dir!r}")
    return Tokenizer.from_file(tok_path)


# ---------------------------------------------------------------------------
# Embedding: mean pooling + L2 normalize
# ---------------------------------------------------------------------------


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    """Normaliza cada linha por L2; vetor zero permanece zero (sem NaN)."""
    norms = np.linalg.norm(v, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    return (v / norms).astype(np.float32)


def embed_texts(
    onnx_dir: str,
    texts: list[str] | str,
    batch: int = 16,
    max_len: int = 256,
    prefix: str = "",
) -> np.ndarray:
    """Embute ``texts`` com o modelo em ``onnx_dir``.

    Devolve ``(n, dim)`` em float32, com mean pooling (mascarado) e
    normalização L2. ``prefix`` é anteposto a cada texto (usado p/ modelos
    ``e5``: ``"query: "`` p/ queries, ``"passage: "`` p/ documentos).
    """
    session = _build_session(onnx_dir)
    tokenizer = _build_tokenizer(onnx_dir)
    # O tokenizer.json de alguns modelos traz truncation=128 gravada no arquivo.
    # Desligamos para que o corte seja decidido por max_len (e medível).
    if hasattr(tokenizer, "no_truncation"):
        tokenizer.no_truncation()
    input_names = {i.name for i in session.get_inputs()}

    texts = [texts] if isinstance(texts, str) else list(texts)
    batch = max(1, int(batch))
    max_len = max(1, int(max_len))

    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), batch):
        chunk = texts[start : start + batch]
        to_encode = [f"{prefix}{t}" for t in chunk] if prefix else list(chunk)
        encoded = tokenizer.encode_batch(to_encode)
        if not encoded:
            continue

        max_length = max(1, min(max(len(enc.ids) for enc in encoded), max_len))
        n = len(chunk)
        input_ids = np.zeros((n, max_length), dtype=np.int64)
        attention_mask = np.zeros((n, max_length), dtype=np.int64)
        token_type_ids = np.zeros((n, max_length), dtype=np.int64)
        for i, enc in enumerate(encoded):
            L = min(len(enc.ids), max_length)
            input_ids[i, :L] = enc.ids[:L]
            attention_mask[i, :L] = enc.attention_mask[:L]
            type_ids = getattr(enc, "type_ids", None)
            if type_ids and len(type_ids) >= L:
                token_type_ids[i, :L] = type_ids[:L]

        ort_inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        }
        # some models (ex.: granite/modernbert) não declaram token_type_ids
        ort_inputs = {k: v for k, v in ort_inputs.items() if k in input_names}

        outputs = session.run(None, ort_inputs)
        last = np.asarray(outputs[0], dtype=np.float32)  # (n, seq, dim)

        mask = attention_mask[..., np.newaxis].astype(np.float32)
        sum_emb = np.sum(last * mask, axis=1)
        sum_mask = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
        chunks.append(_l2_normalize(sum_emb / sum_mask))

    if not chunks:
        return np.zeros((0, 0), dtype=np.float32)
    return np.vstack(chunks)


# ---------------------------------------------------------------------------
# Busca por similaridade de cosseno
# ---------------------------------------------------------------------------


def topk_positions(corpus_emb: np.ndarray, query_emb: np.ndarray, k: int) -> list[int]:
    """Índices (0-based) dos ``k`` documentos de maior cosseno com a query.

    Robusto a vetores não normalizados (e a query zero). Desempate estável:
    índice menor primeiro. ``k`` limitado ao tamanho do corpus.
    """
    corpus_emb = np.asarray(corpus_emb, dtype=np.float32)
    query_emb = np.asarray(query_emb, dtype=np.float32)
    n = corpus_emb.shape[0]
    k = max(0, min(int(k), n))
    if k == 0 or n == 0:
        return []

    cn = np.linalg.norm(corpus_emb, axis=1, keepdims=True)
    cn = np.where(cn < 1e-12, 1.0, cn)
    c = corpus_emb / cn
    qn = float(np.linalg.norm(query_emb))
    q = query_emb / qn if qn > 1e-12 else np.zeros_like(query_emb)

    sims = c @ q
    order = np.argsort(-sims, kind="stable")
    return [int(i) for i in order[:k]]


# ---------------------------------------------------------------------------
# Métricas: recall@k / mrr@k por gold_hash no top-k
# ---------------------------------------------------------------------------


def recall_mrr(
    positions: dict[str, list[int]],
    corpus_hashes: list[str],
    cases: list[dict],
    k: int = 10,
) -> dict:
    """Agrega recall@k / mrr@k e as posições de acerto por caso.

    ``positions[case_id]`` é a lista de índices de corpus (em ordem de rank,
    top primeiro). Acerto = o primeiro índice cujo ``corpus_hashes[idx]`` pertence
    a ``case["gold_hashes"]``. Posição é 1-based; acerto além do top-k é miss.
    """
    k = int(k)
    hash_list = list(corpus_hashes)

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
                if hash_list[idx] in gold:
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


# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------


def load_corpus(db_path: str, store: str | None = "default") -> list[tuple[str, str]]:
    """Memórias vivas de conteúdo não vazio como ``[(content_hash, content)]``.

    Abre o snapshot em ``mode=ro`` (R6). Ordem determinística por ``rowid`` —
    os índices do vetor de embeddings casam com ``corpus_hashes`` na mesma ordem.

    ``store`` replica o filtro do serviço: ``retrieve()`` usa ``store='default'``
    por padrão, então o A/B precisa do mesmo recorte para ser comparável ao
    harness. ``store=None`` usa o acervo inteiro.
    """
    sql = _CORPUS_SQL
    params: tuple = ()
    if store is not None:
        sql = sql.replace("ORDER BY rowid", "AND store = ? ORDER BY rowid")
        params = (store,)
    conn = sqlite3.connect(_RO_URI.format(path=db_path), uri=True)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [(str(h), str(c)) for h, c in rows]


def load_cases(path: str) -> list[dict]:
    """Carrega o dataset (formato de ``eval/recall_cases.json``) e o valida.

    Aceita objeto com chave ``cases`` (ou lista direta). Cada caso precisa de
    ``id``, ``pergunta`` e (``gold_terms`` OU ``gold_hashes``) não vazios.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError(f"dataset {path!r} malformado: esperado 'cases' (lista)")

    loaded: list[dict] = []
    for idx, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"caso {idx} não é um objeto JSON")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"caso {idx} sem 'id' válido")
        pergunta = case.get("pergunta")
        if not isinstance(pergunta, str) or not pergunta.strip():
            raise ValueError(f"caso '{case_id}' sem 'pergunta'")
        terms = case.get("gold_terms")
        hashes = case.get("gold_hashes")
        has_terms = isinstance(terms, list) and any(isinstance(t, str) and t.strip() for t in terms)
        has_hashes = isinstance(hashes, list) and any(isinstance(h, str) and h.strip() for h in hashes)
        if not has_terms and not has_hashes:
            raise ValueError(f"caso '{case_id}' sem 'gold_terms' nem 'gold_hashes'")
        loaded.append(case)
    return loaded


# ---------------------------------------------------------------------------
# Parsing dos modelos da CLI
# ---------------------------------------------------------------------------


def _parse_prefix_spec(spec: str | None) -> tuple[str, str]:
    """Converte a spec de prefixo em ``(query_prefix, passage_prefix)``.

    * ``None``/``""``/``"none"`` → sem prefixo.
    * ``"query/passage"`` → ``("query: ", "passage: ")`` (padrão e5).
    * ``"A/B"`` (literais) → ``(A, B)``.
    * ``"A"`` (único) → ``(A, A)``.
    """
    if spec is None:
        return "", ""
    spec = spec.strip()
    if spec.lower() in ("", "none", "no"):
        return "", ""

    def _resolve(seg: str) -> str:
        seg = seg.strip()
        if seg == "query":
            return "query: "
        if seg == "passage":
            return "passage: "
        if seg in ("", "-", "none"):
            return ""
        return seg  # prefixo literal

    parts = spec.split("/", 1)
    if len(parts) == 1:
        q = _resolve(parts[0])
        return q, q
    return _resolve(parts[0]), _resolve(parts[1])


def _parse_model_spec(spec: str) -> dict:
    """``nome=dir[,prefixo=Q/P]`` → dict com name/dir/prefixos.

    Formato (repetível via ``--model``):
      * ``atual=/path/dir`` — sem prefixo.
      * ``e5=/path/dir,prefixo=query/passage`` — prefixos e5.
    """
    if "=" not in spec:
        raise ValueError(f"--model malformado {spec!r}: esperado nome=dir[,prefixo=Q/P]")
    name, rest = spec.split("=", 1)
    name = name.strip()
    if not name:
        raise ValueError(f"--model sem nome: {spec!r}")

    dir_path: str | None = None
    prefix_spec: str | None = None
    for part in rest.split(","):
        p = part.strip()
        if p.startswith("prefixo="):
            prefix_spec = p[len("prefixo=") :]
        elif p:
            dir_path = p
    if not dir_path:
        raise ValueError(f"--model sem diretório: {spec!r}")

    query_prefix, passage_prefix = _parse_prefix_spec(prefix_spec)
    return {
        "name": name,
        "dir": dir_path,
        "query_prefix": query_prefix,
        "passage_prefix": passage_prefix,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_table(results: dict[str, dict], k: int) -> None:
    rk = f"recall@{k}"
    mk = f"mrr@{k}"
    header = f"{'modelo':<14} {'dim':>4} {rk:>10} {mk:>9} {'ms/emb':>9} {'total_s':>9}"
    print("\n" + header, file=sys.stderr)
    print("-" * len(header), file=sys.stderr)
    for name in results:
        r = results[name]
        print(
            f"{name:<14} {r['dim']:>4} {r[rk]:>10.3f} {r[mk]:>9.3f} "
            f"{r['ms_per_embedding']:>9.3f} {r['total_s']:>9.2f}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    """CLI: ``--db --cases --model nome=dir[,prefixo=Q/P] --out --k``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="model_ab",
        description=(
            "A/B de modelos de embedding: embute o snapshot (read-only) e as queries "
            "com cada modelo ONNX local e mede recall@k / mrr@k por similaridade de cosseno."
        ),
    )
    parser.add_argument("--db", required=True, help="snapshot SQLite (read-only)")
    parser.add_argument(
        "--cases", default="eval/recall_cases.json", help="dataset de casos (padrão eval/recall_cases.json)"
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        required=True,
        help=(
            "nome=dir[,prefixo=Q/P] (REPETÍVEL). Ex.: --model atual=/path/dir ; "
            "--model e5-small=/path/e5-small,prefixo=query/passage"
        ),
    )
    parser.add_argument("--out", default=None, help="grava o relatório JSON neste arquivo")
    parser.add_argument("--k", type=int, default=10, help="top-k (padrão 10)")
    parser.add_argument(
        "--max-len",
        type=int,
        default=256,
        help="tokens máximos por texto (padrão 256; 128 = regime do modelo atual)",
    )
    parser.add_argument(
        "--store",
        default="default",
        help="partição de memória (padrão 'default', igual ao retrieve do serviço; 'all' = acervo inteiro)",
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.db):
        print(f"erro: snapshot não encontrado em {args.db!r}", file=sys.stderr)
        return 2

    try:
        models = [_parse_model_spec(s) for s in args.model]
    except ValueError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    if not models:
        print("erro: passe ao menos um --model", file=sys.stderr)
        return 2

    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"erro: dataset inválido: {exc}", file=sys.stderr)
        return 2

    try:
        corpus = load_corpus(args.db, None if args.store == "all" else args.store)
    except sqlite3.Error as exc:
        print(f"erro: não foi possível ler o snapshot: {exc}", file=sys.stderr)
        return 2
    if not corpus:
        print("erro: snapshot sem memórias vivas de conteúdo não vazio", file=sys.stderr)
        return 1

    corpus_hashes = [h for h, _ in corpus]
    corpus_texts = [c for _, c in corpus]
    queries = [case["pergunta"] for case in cases]

    results: dict[str, dict] = {}
    for model in models:
        t0 = time.perf_counter()

        t = time.perf_counter()
        corpus_emb = embed_texts(
            model["dir"], corpus_texts, batch=64, max_len=args.max_len,
            prefix=model["passage_prefix"],
        )
        corpus_ms = time.perf_counter() - t

        t = time.perf_counter()
        query_emb = embed_texts(
            model["dir"], queries, batch=16, max_len=args.max_len,
            prefix=model["query_prefix"],
        )
        query_ms = time.perf_counter() - t

        dim = int(corpus_emb.shape[1]) if corpus_emb.size else 0

        positions: dict[str, list[int]] = {}
        for i, case in enumerate(cases):
            positions[str(case["id"])] = topk_positions(corpus_emb, query_emb[i], args.k)
        metrics = recall_mrr(positions, corpus_hashes, cases, k=args.k)

        total_embeds = len(corpus_texts) + len(queries)
        total_embed_s = corpus_ms + query_ms
        entry = {
            "dir": model["dir"],
            "query_prefix": model["query_prefix"],
            "passage_prefix": model["passage_prefix"],
            "dim": dim,
            "n_corpus": len(corpus_texts),
            "n_queries": len(queries),
            "corpus_embed_s": round(corpus_ms, 3),
            "query_embed_s": round(query_ms, 3),
            "ms_per_embedding": round(total_embed_s * 1000.0 / total_embeds, 4) if total_embeds else 0.0,
            "total_s": round(time.perf_counter() - t0, 3),
        }
        entry.update(metrics)
        results[model["name"]] = entry
        print(
            f"[model_ab] {model['name']}: dim={dim} corpus={corpus_ms:.1f}s "
            f"query={query_ms:.3f}s recall@{args.k}={metrics[f'recall@{args.k}']:.3f}",
            file=sys.stderr,
        )

    report = {
        "meta": {
            "db": args.db,
            "cases": args.cases,
            "k": args.k,
            "n_corpus": len(corpus),
            "n_cases": len(cases),
        },
        "models": results,
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
