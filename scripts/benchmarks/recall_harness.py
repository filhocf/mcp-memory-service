"""Harness de Recall@k para ``memory_search`` com perguntas naturais (I2 / G4).

Contrato público fixado por ``tests/test_recall_harness.py``
(spec ``docs/rfc/planned/spec-recall-harness.md``):

  * ``load_cases(path) -> list[dict]``
  * ``validate_cases(cases, conn) -> (validos, invalidos)``
  * ``posicao_do_acerto(resultados, gold_terms) -> int | None``
  * ``evaluate(cases, runner, k=10) -> dict``
  * ``compare(report_a, report_b) -> dict``
  * ``make_runner(db_path) -> callable(query, mode, limit) -> list[dict]``
  * ``main(argv) -> int``

Decisões fixadas (diário de gate, spec §8):
  * Acerto POR CONTEÚDO: substring de ``gold_term`` (case-insensitive) no
    ``content`` do resultado — não por ``content_hash``.
  * Quatro modos sempre: ``semantic``, ``exact``, ``hybrid``, ``ranked``.
  * Execução LEITURA-SOMENTE: o SQLite é aberto com ``mode=ro`` (R6). As
    tentativas de escrita internas do storage (persistência de acesso,
    telemetria de uso) falham inofensivamente contra a conexão read-only —
    nenhuma mutação de estado é possível.
  * Determinismo (R5): o relatório não carrega timestamps; modos, case ids,
    categorias e avisos saem ordenados; ``json.dumps(sort_keys=True)`` idêntico
    entre execuções com a mesma entrada.

Uso (CLI, a partir da raiz do worktree):

  python -m scripts.benchmarks.recall_harness --db <snapshot> --out /tmp/r.json
  python -m scripts.benchmarks.recall_harness compare --a r1.json --b r2.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys

# Reuso de métricas de scripts/benchmarks/locomo_evaluator.py:11-40.
# Import plano quando o diretório está no sys.path (convenção dos testes);
# relativo quando este módulo roda como ``scripts.benchmarks.recall_harness``.
try:  # pragma: no cover - trivial import fallback
    from locomo_evaluator import mrr, recall_at_k
except ImportError:  # pragma: no cover
    from .locomo_evaluator import mrr, recall_at_k

#: Os quatro modos medidos, na ordem canônica (sortida, p/ determinismo).
MODES = ("exact", "hybrid", "ranked", "semantic")

#: Marcador emitido pelo servidor quando um resultado é truncado (spec §5).
TRUNCATION_MARKER = "[!] RESPONSE TRUNCATED"

#: Prefixo URI SQLite para conexões somente-leitura.
_RO_URI = "file:{path}?mode=ro"

#: SQL de validação do gabarito (R2): contagem de memórias vivas cujo conteúdo
#: contém o termo (case-insensitive, com escaping de LIKE).
_GOLD_TERM_COUNT_SQL = (
    "SELECT COUNT(*) FROM memories "
    "WHERE deleted_at IS NULL AND content LIKE ? ESCAPE '\\' COLLATE NOCASE"
)


class ModeUnavailable(RuntimeError):
    """Um modo de busca falhou no backend (registro 'unavailable', spec §5)."""


# ---------------------------------------------------------------------------
# R1 — dataset versionado e verificável
# ---------------------------------------------------------------------------


def load_cases(path: str) -> list[dict]:
    """Carrega o dataset versionado (formato de ``eval/recall_cases.json``).

    VALIDA que cada caso declara ``id``, ``pergunta`` e ``gold_terms`` não
    vazio; caso contrário levanta ``ValueError`` com o caso problemático.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError(
            f"dataset {path!r} malformado: esperado objeto com chave 'cases' "
            "(ou lista de casos)"
        )

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
        if not isinstance(terms, list) or not terms:
            raise ValueError(f"caso '{case_id}' sem 'gold_terms' (lista não vazia)")
        if not all(isinstance(t, str) and t.strip() for t in terms):
            raise ValueError(
                f"caso '{case_id}' com 'gold_terms' contendo entrada inválida "
                "(toda entrada deve ser string não vazia)"
            )
        loaded.append(case)
    return loaded


# ---------------------------------------------------------------------------
# R2 — verificação do gabarito antes de medir
# ---------------------------------------------------------------------------


def _escape_like(term: str) -> str:
    """Escapa metacaracteres de LIKE (``\\``, ``%``, ``_``) para ``ESCAPE '\\``'."""
    return (
        term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


def _count_live_matches(conn, term: str) -> int:
    """Memórias vivas (``deleted_at IS NULL``) cujo conteúdo contém o termo."""
    pattern = f"%{_escape_like(term)}%"
    row = conn.execute(_GOLD_TERM_COUNT_SQL, (pattern,)).fetchone()
    return int(row[0]) if row else 0


def validate_cases(cases: list[dict], conn) -> tuple[list[dict], list[dict]]:
    """Verifica o gabarito contra o banco (LEITURA SOMENTE — R6).

    Um caso é inválido quando qualquer ``gold_term`` não aparece no
    ``content`` de nenhuma memória viva. Inválidos levam a chave
    ``missing_terms`` com os termos ausentes. Nenhuma escrita é emitida
    (nem ``commit``).
    """
    validos: list[dict] = []
    invalidos: list[dict] = []
    for case in cases:
        missing = [
            term
            for term in case.get("gold_terms", [])
            if _count_live_matches(conn, term) == 0
        ]
        if missing:
            entry = dict(case)
            entry["missing_terms"] = missing
            invalidos.append(entry)
        else:
            validos.append(case)
    return validos, invalidos


# ---------------------------------------------------------------------------
# R3 — posição do primeiro acerto (por conteúdo, não por hash)
# ---------------------------------------------------------------------------


def posicao_do_acerto(resultados: list[dict], gold_terms: list[str]) -> int | None:
    """Posição 1-based do PRIMEIRO resultado cujo ``content`` contém um termo.

    Match case-insensitive por substring, avaliado sobre o conteúdo do
    resultado (nunca sobre ``content_hash``). ``None`` quando nenhum
    resultado contém qualquer termo.
    """
    terms = [t.lower() for t in gold_terms if t]
    for pos, result in enumerate(resultados, start=1):
        content = str(result.get("content") or "").lower()
        if any(t in content for t in terms):
            return pos
    return None


# ---------------------------------------------------------------------------
# R4 — métricas padronizadas (reuso de recall_at_k / mrr do locomo_evaluator)
# ---------------------------------------------------------------------------


def _per_case_metrics(resultados: list[dict], gold_terms: list[str], k: int) -> tuple[float, float, int | None]:
    """Recall@k, MRR@k e posição do primeiro acerto para UM caso.

    Constrói a bandeira ``HIT``/``MISS`` por resultado (top-k) e delega a
    ``recall_at_k``/``mrr`` de ``locomo_evaluator`` (reuso da spec R4):
    com ``relevant={"HIT"}`` e ``k`` resultados, ``recall_at_k`` = 1.0 se o
    caso tem acerto no top-k; ``mrr`` = 1/posição do primeiro acerto.
    """
    flags = []
    for result in resultados[:k]:
        content = str(result.get("content") or "").lower()
        hit = any(t.lower() in content for t in gold_terms if t)
        flags.append("HIT" if hit else "MISS")
    case_recall = recall_at_k(flags, {"HIT"}, k) if flags else 0.0
    case_mrr = mrr(flags, {"HIT"}) if flags else 0.0
    position = posicao_do_acerto(resultados, gold_terms)
    return case_recall, case_mrr, position


def _mode_metrics(positions: dict[str, int | None], n_cases: int, k: int) -> tuple[float, float]:
    """recall@k / mrr@k agregando posições por caso (média uniforme)."""
    if n_cases == 0:
        return 0.0, 0.0
    recalls = []
    reciprocals = []
    for pos in positions.values():
        if pos is not None and pos <= k:
            recalls.append(1.0)
            reciprocals.append(1.0 / pos)
        else:
            recalls.append(0.0)
            reciprocals.append(0.0)
    return sum(recalls) / n_cases, sum(reciprocals) / n_cases


def evaluate(cases: list[dict], runner, k: int = 10) -> dict:
    """Executa os quatro modos sobre cada caso e agrega métricas.

    ``runner(pergunta: str, mode: str, limit: int) -> list[dict]`` (cada
    resultado tem no mínimo a chave ``content``). Se o runner levanta
    ``ModeUnavailable`` (ou qualquer exceção) num modo, o modo é registrado
    como ``"unavailable"`` e os demais seguem (spec §5).

    A saída é determinística: chaves ordenadas (modos, case ids, categorias),
    sem timestamps (R5).
    """
    k = int(k)
    cases_sorted = sorted(cases, key=lambda c: str(c["id"]))
    categories = sorted({str(c.get("categoria") or "unknown") for c in cases_sorted})

    warnings: set[str] = set()
    modes_report: dict[str, dict] = {}

    for mode in MODES:  # já ordenada
        positions: dict[str, int | None] = {}
        status = "ok"
        error: str | None = None
        for case in cases_sorted:
            case_id = str(case["id"])
            try:
                resultados = runner(case["pergunta"], mode, k)
            except ModeUnavailable as exc:
                status = "unavailable"
                error = str(exc)
                break
            except Exception as exc:  # backend fora do ar: não quebra os demais
                status = "unavailable"
                error = f"{type(exc).__name__}: {exc}"
                break
            if resultados is None:
                resultados = []
            for result in resultados:
                if TRUNCATION_MARKER in str(result.get("content") or ""):
                    warnings.add(f"{mode}/{case_id}: resultado truncado pelo servidor")
            positions[case_id] = posicao_do_acerto(resultados, case.get("gold_terms", []))

        n_cases = len(cases_sorted)
        recall, mrr_value = _mode_metrics(positions, n_cases, k)
        mode_entry: dict = {
            "status": status,
            f"recall@{k}": recall,
            f"mrr@{k}": mrr_value,
            "positions": positions,  # inserido em ordem de case id (sortido)
        }
        if error is not None:
            mode_entry["error"] = error
        modes_report[mode] = mode_entry

    # Métricas por categoria (R4) — apenas para modos disponíveis.
    by_category: dict[str, dict] = {}
    for cat in categories:
        cat_cases = [c for c in cases_sorted if str(c.get("categoria") or "unknown") == cat]
        cat_entry: dict[str, dict] = {}
        for mode in MODES:
            mode_info = modes_report[mode]
            if mode_info["status"] == "unavailable":
                continue
            pos = {str(c["id"]): mode_info["positions"].get(str(c["id"])) for c in cat_cases}
            recall, mrr_value = _mode_metrics(pos, len(cat_cases), k)
            cat_entry[mode] = {
                f"recall@{k}": recall,
                f"mrr@{k}": mrr_value,
                "n_cases": len(cat_cases),
            }
        by_category[cat] = cat_entry

    return {
        "meta": {
            "k": k,
            "n_cases": len(cases_sorted),
            "n_categories": len(categories),
        },
        "modes": modes_report,
        "by_category": by_category,
        "warnings": sorted(warnings),
    }


# ---------------------------------------------------------------------------
# R7 — comparação A/B entre execuções
# ---------------------------------------------------------------------------


def compare(report_a: dict, report_b: dict) -> dict:
    """Compara dois relatórios (formato de :func:`evaluate`).

    Retorna deltas (B - A) de recall/MRR por modo e os cases cuja posição do
    primeiro acerto mudou em qualquer modo (ordenado). Chaves ausentes
    (ex.: modo inexistente/indisponível num dos relatórios) valem 0.0 / None.
    """
    modes = sorted(set(report_a.get("modes", {})) | set(report_b.get("modes", {})))
    deltas: dict[str, dict] = {}
    changed: set[str] = set()

    for mode in modes:
        a_mode = report_a.get("modes", {}).get(mode, {})
        b_mode = report_b.get("modes", {}).get(mode, {})
        metric_keys = sorted(
            {k for k in a_mode if k not in ("positions", "status", "error")}
            | {k for k in b_mode if k not in ("positions", "status", "error")}
        )
        deltas[mode] = {
            key: float(b_mode.get(key, 0.0)) - float(a_mode.get(key, 0.0))
            for key in metric_keys
        }
        pos_a = a_mode.get("positions", {})
        pos_b = b_mode.get("positions", {})
        for case_id in set(pos_a) | set(pos_b):
            if pos_a.get(case_id) != pos_b.get(case_id):
                changed.add(str(case_id))

    return {"deltas": deltas, "changed_cases": sorted(changed)}


# ---------------------------------------------------------------------------
# Runner sobre o storage real (read-only)
# ---------------------------------------------------------------------------

#: Candidatos para a deteccao do modelo de embedding do corpus (ordem fixa,
#: modelos ja usados historicamente por este servico).
_MODEL_CANDIDATES = (
    "all-MiniLM-L6-v2",
    "paraphrase-multilingual-MiniLM-L12-v2",
)

#: Amostra de memorias usada nos probe queries de deteccao.
_DETECT_SAMPLE_SIZE = 16

#: Composicao por coorte da ultima deteccao (diagnostico: corpus misto).
_LAST_COHORTS: dict = {}

#: Cosine medio minimo para concluir que o candidato produziu o corpus.
#: O modelo correto re-produz o vetor (cosine ~= 1.0); modelos errados dao
#: ~0.3-0.5 — a margem e larga o suficiente para nao confundir.
_DETECT_MIN_MEAN_COSINE = 0.90


def _detect_corpus_model(db_path: str):
    """Detecta qual modelo de embedding produziu os vetores do corpus.

    Probe queries read-only: amostra 16 memorias vivas (store default,
    nao-pending) em ordem deterministica (``rowid DESC``), re-encode o
    conteudo com cada candidato ONNX e mede o cosine medio contra o vetor
    guardado em ``memory_embeddings``.

    Retorna ``(nome | None, scores, model_instance | None)`` — ``None``
    quando nenhum candidato alcana o limiar (corpus embedido por modelo
    externo/desconhecido; os modos semanticos ficam 'unavailable').
    """
    import numpy as np
    import sqlite_vec

    from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model

    def _ro_vec_conn():
        conn = sqlite3.connect(_RO_URI.format(path=db_path), uri=True)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    conn = _ro_vec_conn()
    try:
        # Amostra ESTRATIFICADA, não as N mais recentes: o corpus pode estar
        # partido em coortes (memórias antigas vetorizadas por um modelo, novas
        # por outro). Amostrar a cauda faz a detecção enxergar só a coorte nova
        # e escolher o modelo errado para o acervo inteiro.
        total = conn.execute(
            "SELECT COUNT(*) FROM memories m "
            "WHERE m.deleted_at IS NULL AND m.store = 'default' "
            "AND (m.embedding_pending IS NULL OR m.embedding_pending = 0)"
        ).fetchone()[0]
        sample = []
        if total:
            step = max(total // _DETECT_SAMPLE_SIZE, 1)
            offsets = list(range(0, total, step))[:_DETECT_SAMPLE_SIZE]
            for off in offsets:
                row = conn.execute(
                    "SELECT m.rowid, m.content FROM memories m "
                    "WHERE m.deleted_at IS NULL AND m.store = 'default' "
                    "AND (m.embedding_pending IS NULL OR m.embedding_pending = 0) "
                    "ORDER BY m.rowid LIMIT 1 OFFSET ?",
                    (off,),
                ).fetchone()
                if row is not None:
                    sample.append(row)
    finally:
        conn.close()
    if not sample:
        return None, {}, None

    stored_vecs = []
    conn = _ro_vec_conn()
    try:
        for rowid, _content in sample:
            row = conn.execute(
                "SELECT content_embedding FROM memory_embeddings WHERE rowid = ?",
                (rowid,),
            ).fetchone()
            if row is None or row[0] is None:
                return None, {}, None
            stored_vecs.append(np.frombuffer(row[0], dtype=np.float32).copy())
    finally:
        conn.close()

    env_model = os.environ.get("MCP_EMBEDDING_MODEL")
    candidates = []
    for name in ([env_model] if env_model else []) + list(_MODEL_CANDIDATES):
        if name not in candidates:
            candidates.append(name)

    texts = [content for _rowid, content in sample]
    scores: dict[str, float] = {}
    instances: dict[str, object] = {}
    sim_matrix: dict[str, list[float]] = {}
    for name in candidates:
        model = get_onnx_embedding_model(name)
        if model is None:
            continue
        try:
            emb = np.asarray(model.encode(texts, convert_to_numpy=True), dtype=np.float32)
        except Exception:
            continue
        if emb.shape != (len(stored_vecs), stored_vecs[0].size):
            continue
        sims = []
        for i, stored in enumerate(stored_vecs):
            na = float(np.linalg.norm(emb[i]))
            nb = float(np.linalg.norm(stored))
            sims.append(float(np.dot(emb[i], stored) / (na * nb)) if na and nb else 0.0)
        scores[name] = float(np.mean(sims))
        sim_matrix[name] = sims
        instances[name] = model

    if not scores:
        return None, {}, None

    # Composição por coorte: quantas memórias da amostra cada modelo reproduz
    # EXATAMENTE (cosine >= 0.99) e quantas nenhum reproduz (vetor órfão, de
    # modelo fora da lista). Com corpus misto a média engana; a contagem não.
    names = list(sim_matrix)
    cohorts: dict[str, int] = {n: 0 for n in names}
    cohorts["nenhum"] = 0
    for i in range(len(texts)):
        exact = [n for n in names if sim_matrix[n][i] >= 0.99]
        if not exact:
            cohorts["nenhum"] += 1
            continue
        winner = max(exact, key=lambda n: sim_matrix[n][i])
        cohorts[winner] += 1
    _LAST_COHORTS.clear()
    _LAST_COHORTS.update({"amostra": len(texts), "coortes": cohorts})

    # Decisão por maioria de coorte (não pela média): com 64%/36% de corpus
    # misto a média pode eleger o modelo minoritário-tardio. A média do corpus
    # inteiro nunca chega a 0.90 quando há mistura, então o critério de aceitação
    # é a média DENTRO da coorte do candidato.
    best = max(
        [n for n in names] + ["nenhum"],
        key=lambda k: cohorts.get(k, 0),
    )
    if best in sim_matrix and cohorts.get(best, 0) / max(len(texts), 1) >= 0.5:
        own = [
            sim_matrix[best][i]
            for i in range(len(texts))
            if sim_matrix[best][i] >= 0.99
        ]
        if own and float(np.mean(own)) >= _DETECT_MIN_MEAN_COSINE:
            return best, scores, instances[best]
    best = max(scores.items(), key=lambda kv: kv[1])[0]
    if scores[best] < _DETECT_MIN_MEAN_COSINE:
        return None, scores, None
    return best, scores, instances[best]


def _prewarm_model_cache(model_name: str, instance=None) -> None:
    """Deixa a instancia de modelo ja carregada no cache do storage.

    O storage keya o cache por ``onnx_{embedding_model_name}``; sem isto o
    harness pagaria o load do ONNX duas vezes (deteccao + storage).
    """
    try:
        from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model
        from mcp_memory_service.storage.mixins.embeddings import _MODEL_CACHE, _DIMENSION_CACHE
    except Exception:
        return
    key = f"onnx_{model_name}"
    if key in _MODEL_CACHE:
        return
    model = instance if instance is not None else get_onnx_embedding_model(model_name)
    if model is None:
        return
    _MODEL_CACHE[key] = model
    if hasattr(model, "embedding_dimension"):
        _DIMENSION_CACHE[key] = model.embedding_dimension


def _make_readonly_storage_class():
    """Classe de storage read-only (import tardio: só o runner precisa dela)."""
    from mcp_memory_service.storage.mixins.base import DictRow
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage

    class _ReadOnlySqliteVecStorage(SqliteVecMemoryStorage):
        """Abre o snapshot em ``mode=ro`` e pula migrações de schema.

        O snapshot é um banco já migrado pelo serviço em produção; o
        override de ``initialize`` conecta, carrega o sqlite-vec e o modelo
        de embedding e não emite nenhuma DDL (garantia extra de R6).
        """

        def _connect_and_load_extension(self):
            self.conn = sqlite3.connect(
                _RO_URI.format(path=self.db_path),
                uri=True,
                check_same_thread=False,
            )
            self.conn.row_factory = DictRow
            self._load_sqlite_vec_extension()
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.execute("PRAGMA cache_size=10000")

        async def initialize(self, strict_dimension_check: bool = True):
            if self._initialized:
                return
            self._check_dependencies()
            supported, _message = self._check_extension_support()
            if not supported:
                self._handle_extension_loading_failure()
            await self._run_in_thread(self._connect_and_load_extension)
            await self._initialize_embedding_model()
            self._initialized = True

    return _ReadOnlySqliteVecStorage


def _search_via_storage(storage_cls, db_path: str, query: str, mode: str, limit: int,
                        model_name: str | None = None) -> list[dict]:
    """Uma busca completa (init + search_memories) em um único loop asyncio."""

    async def _once() -> dict:
        # O storage precisa do MESMO modelo que produziu o corpus: a instância
        # do servico (server_impl.py / storage/factory.py) passa
        # ``embedding_model=EMBEDDING_MODEL_NAME`` no construtor. Sem isto a
        # query é embedida com all-MiniLM-L6-v2 e o ranking KNN fica errado.
        if model_name:
            storage = storage_cls(db_path, embedding_model=model_name)
        else:
            storage = storage_cls(db_path)
        await storage.initialize(strict_dimension_check=False)
        return await storage.search_memories(query=query, mode=mode, limit=limit)

    result = asyncio.run(_once())
    if not isinstance(result, dict):
        raise ModeUnavailable(f"storage retornou resultado inesperado: {type(result)!r}")
    if result.get("error"):
        raise ModeUnavailable(str(result["error"]))
    memories = result.get("memories") or []
    return [m for m in memories if isinstance(m, dict) and "content" in m]


def _search_exact_sql(conn, query: str, limit: int) -> list[dict]:
    """Fallback read-only do modo ``exact`` (mesma semântica de SQL do storage)."""
    sql = (
        "SELECT content, content_hash FROM memories "
        "WHERE content LIKE '%' || ? || '%' ESCAPE '\\' COLLATE NOCASE "
        "AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT ?"
    )
    rows = conn.execute(sql, (_escape_like(query), limit)).fetchall()
    return [{"content": r[0], "content_hash": r[1]} for r in rows]


def make_runner(db_path: str, embedding_model: str | None = None):
    """Cria o runner ``(query, mode, limit) -> list[dict]`` sobre o storage real.

    * A conexão SQLite é aberta em ``mode=ro``: nenhuma escrita é possível.
    * Resolução do modelo de embedding (a query precisa do MESMO modelo que
      produziu o corpus — senão o KNN sem sentido nenhum):
      1. ``embedding_model`` explícito (CLI ``--embedding-model``);
      2. env ``MCP_EMBEDDING_MODEL`` (mesma fonte da instância de produção);
      3. detecao por probe queries no próprio snapshot (read-only,
         deterministica);
      sem nenhuma das três, os modos semanticos ficam ``unavailable`` com
      erro claro (o modo ``exact`` segue funcionando via SQL).
    * ``semantic``/``hybrid``/``ranked`` usam o storage real
      (``SqliteVecMemoryStorage``, store ``default``, limit ``k``); falhas de
      backend levantam :class:`ModeUnavailable` e ``evaluate`` registra
      ``unavailable`` sem quebrar os demais.
    * ``exact`` usa o storage real quando disponível e cai para SQL puro
      (read-only, mesma semântica) caso contrário.
    * Cada resultado retornado é o dict de memória do storage (contém no
      mínimo ``content`` e ``content_hash``) — a "lista de conteúdos".
    * ``runner.effective_config`` expõe a configuração efetiva usada
      (modelo + origem + fusao híbrida) para o relatório.
    """
    state: dict = {"storage_cls": None, "storage_error": None, "plain_conn": None}
    model_info: dict = {
        "name": None,
        "source": None,
        "detection_scores": {},
    }

    def _storage_cls():
        if state["storage_cls"] is None and state["storage_error"] is None:
            try:
                # Telemetria de uso desligada: menos tentativas de escrita
                # (que falham inofensivamente contra mode=ro).
                os.environ.setdefault("MCP_USAGE_TELEMETRY", "false")
                state["storage_cls"] = _make_readonly_storage_class()
            except Exception as exc:
                state["storage_error"] = f"{type(exc).__name__}: {exc}"
        return state["storage_cls"]

    def _plain_conn():
        if state["plain_conn"] is None:
            state["plain_conn"] = sqlite3.connect(
                _RO_URI.format(path=db_path), uri=True
            )
        return state["plain_conn"]

    def _resolve_model() -> None:
        if embedding_model:
            model_info.update(name=embedding_model, source="cli")
            _prewarm_model_cache(embedding_model)
            return
        env_model = os.environ.get("MCP_EMBEDDING_MODEL")
        if env_model:
            model_info.update(name=env_model, source="env")
            _prewarm_model_cache(env_model)
            return
        try:
            detected, scores, instance = _detect_corpus_model(db_path)
            model_info["detection_scores"] = scores
            model_info["name"] = detected
            model_info["source"] = "detected" if detected else "unidentified"
            if detected:
                _prewarm_model_cache(detected, instance)
        except Exception as exc:
            model_info["name"] = None
            model_info["source"] = f"detection_failed: {type(exc).__name__}: {exc}"

    _resolve_model()

    def _effective_config() -> dict:
        config: dict = {
            "embedding_model": model_info["name"],
            "model_source": model_info["source"],
        }
        if model_info["detection_scores"]:
            config["detection_scores"] = {
                k: v for k, v in sorted(model_info["detection_scores"].items())
            }
        if _LAST_COHORTS:
            config["detection_cohorts"] = dict(_LAST_COHORTS.get("coortes") or {})
            config["detection_sample"] = _LAST_COHORTS.get("amostra")
        try:
            from mcp_memory_service.config import search as _cfg_search

            config["hybrid_fusion_method"] = _cfg_search.MCP_HYBRID_FUSION_METHOD
            config["hybrid_rrf_k"] = _cfg_search.MCP_HYBRID_RRF_K
        except Exception:
            pass
        return config

    def runner(query: str, mode: str, limit: int = 10) -> list[dict]:
        limit = int(limit)
        cls = _storage_cls()
        if cls is not None:
            if mode != "exact" and model_info["name"] is None:
                raise ModeUnavailable(
                    f"modo '{mode}' indisponível: modelo de embedding do corpus "
                    f"não identificado ({model_info['source']}) — passe "
                    "--embedding-model ou defina MCP_EMBEDDING_MODEL"
                )
            try:
                return _search_via_storage(
                    cls, db_path, query, mode, limit, model_name=model_info["name"]
                )
            except ModeUnavailable:
                if mode == "exact":
                    pass  # cai para o fallback SQL abaixo
                raise
            except Exception as exc:
                if mode == "exact":
                    pass  # storage fora do ar: fallback SQL puro
                state["storage_error"] = f"{type(exc).__name__}: {exc}"
                raise ModeUnavailable(f"modo '{mode}' indisponível: {exc}") from exc
        if mode == "exact":
            return _search_exact_sql(_plain_conn(), query, limit)
        raise ModeUnavailable(
            f"modo '{mode}' indisponível: storage/embedding não carregou "
            f"({state['storage_error']})"
        )

    runner.effective_config = _effective_config()  # type: ignore[attr-defined]
    return runner


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _dump_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)


def _cmd_compare(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="recall_harness compare")
    parser.add_argument("--a", required=True, help="relatório de referência (antes)")
    parser.add_argument("--b", required=True, help="relatório comparado (depois)")
    parser.add_argument("--out", default=None, help="grava o JSON de deltas neste arquivo")
    args = parser.parse_args(argv)

    with open(args.a, "r", encoding="utf-8") as f:
        report_a = json.load(f)
    with open(args.b, "r", encoding="utf-8") as f:
        report_b = json.load(f)

    payload = _dump_json(compare(report_a, report_b))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI: ``--db PATH --cases PATH --out PATH --k INT`` e subcomando ``compare``."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "compare":
        return _cmd_compare(argv[1:])

    parser = argparse.ArgumentParser(
        prog="recall_harness",
        description="Mede Recall@k / MRR@k de memory_search (4 modos) sobre um snapshot read-only.",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("MCP_BENCH_DB"),
        help="caminho do snapshot SQLite (read-only); padrão: $MCP_BENCH_DB",
    )
    parser.add_argument(
        "--cases", default="eval/recall_cases.json", help="dataset versionado de casos"
    )
    parser.add_argument("--out", default=None, help="grava o relatório JSON neste arquivo")
    parser.add_argument("--k", type=int, default=10, help="top-k (padrão 10)")
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="modelo de embedding explícito (senão: env MCP_EMBEDDING_MODEL, "
        "senão: detecção por probe queries no snapshot)",
    )
    args = parser.parse_args(argv)

    if not args.db:
        print(
            "erro: snapshot ausente — passe --db ou defina MCP_BENCH_DB "
            "(aponte para um snapshot imutável do acervo, não para o banco vivo)",
            file=sys.stderr,
        )
        return 2
    if not os.path.isfile(args.db):
        print(f"erro: snapshot não encontrado em {args.db!r}", file=sys.stderr)
        return 2

    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"erro: dataset inválido: {exc}", file=sys.stderr)
        return 2

    # R2: verificação do gabarito (leitura somente).
    try:
        conn = sqlite3.connect(_RO_URI.format(path=args.db), uri=True)
        try:
            validos, invalidos = validate_cases(cases, conn)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"erro: não foi possível ler o snapshot: {exc}", file=sys.stderr)
        return 2

    invalidos_sorted = sorted(invalidos, key=lambda c: str(c.get("id") or ""))
    runner = make_runner(args.db, embedding_model=args.embedding_model)
    report = evaluate(validos, runner, k=args.k)
    report["invalid_cases"] = [
        {"id": c.get("id"), "missing_terms": c.get("missing_terms", [])}
        for c in invalidos_sorted
    ]
    report["meta"].update(
        {
            "db": args.db,
            "cases": args.cases,
            "n_valid": len(validos),
            "n_invalid": len(invalidos_sorted),
        }
    )

    # Corpus misto: cada coorte vive num espaço vetorial. Sem aviso, o número
    # medido parece do sistema inteiro quando é da coorte majoritária.
    cohorts = dict(_LAST_COHORTS.get("coortes") or {})
    amostra = _LAST_COHORTS.get("amostra") or 0
    if amostra:
        dominante = max(cohorts.values()) if cohorts else 0
        if dominante < amostra:
            minoritarias = {
                k: v for k, v in cohorts.items() if v and k != "nenhum" and v < dominante
            }
            if minoritarias or cohorts.get("nenhum"):
                report.setdefault("warnings", []).append(
                    f"corpus misto na amostra de {amostra}: "
                    + ", ".join(f"{k}={v}" for k, v in sorted(cohorts.items()))
                    + " — a métrica reflete a coorte escolhida; re-embede antes de concluir"
                )
    effective_config = getattr(runner, "effective_config", None)
    if effective_config:
        report["meta"]["effective_config"] = effective_config

    payload = _dump_json(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload + "\n")
    print(payload)

    # Especificação §5: término de busca vazio em TODOS os modos => erro claro.
    if report["meta"]["n_valid"] > 0 and not any(
        any(pos is not None for pos in m["positions"].values())
        for m in report["modes"].values()
    ):
        print(
            "erro: nenhuma busca retornou acerto em nenhum modo — "
            "confira snapshot/modelo de embedding",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
