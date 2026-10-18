"""Testes RED do harness de Recall@k (spec docs/rfc/planned/spec-recall-harness.md §7).

O ALVO a ser implementado no G4 é ``scripts/benchmarks/recall_harness.py``.
Estes testes NÃO implementam o harness — eles fixam o contrato público e devem:

  * FALHAR agora (o módulo não existe): cada teste falha no seu próprio import.
  * Após um GREEN parcial (módulo existe e importa), os testes 3 e 4 devem
    continuar falhando por LÓGICA (métricas/posição erradas), não por import.

Convenções de isolamento:
  * fixtures com SQLite sintético em ``tmp_path`` (tabela ``memories``).
  * nenhum teste toca o acervo real.
  * sem skip/xfail.

CONTRATO PÚBLICO assumido (a ser honrado pelo G4 em scripts/benchmarks/recall_harness.py):

  load_cases(path) -> list[dict]
      Carrega o dataset versionado (formato de eval/recall_cases.json, objeto
      com chave "cases"). VALIDA que cada caso tem ``id``, ``pergunta`` e
      ``gold_terms`` não vazio; caso contrário levanta ValueError (rejeição).

  validate_cases(cases, conn) -> (validos, invalidos)
      Confirma por consulta LEITURA-SOMENTE ao banco (tabela ``memories``) que
      cada ``gold_term`` aparece no ``content`` de >=1 memória viva
      (``deleted_at IS NULL``), case-insensitive. Caso tenha algum gold_term
      inexistente => invalido. Retorna (list[dict], list[dict]) preservando o
      conteúdo dos casos.

  posicao_do_acerto(resultados, gold_terms) -> int | None
      Dado uma lista de resultados (dicts com chave ``content``) e os
      ``gold_terms``, retorna a posição 1-based do PRIMEIRO resultado cujo
      ``content`` contenha qualquer gold_term (case-insensitive, substring).
      Se nenhum resultado contém o termo => None. O acerto é POR CONTEÚDO, não
      por content_hash.

  evaluate(cases, runner, k=10) -> dict
      Para cada caso, executa os 4 modos (semantic, exact, hybrid, ranked) com
      a mesma entrada e registra a posição do primeiro acerto por modo.
      ``runner(pergunta: str, mode: str, limit: int) -> list[dict]`` (cada
      resultado tem no mínimo ``content``). Retorna ao menos::

          {"modes": {<mode>: {"recall@{k}": float, "mrr@{k}": float,
                              "positions": {case_id: int|None}}, ...}}

      Saída determinística e ordenada (mesma entrada => JSON idêntico).

  compare(report_a, report_b) -> dict
      Compara dois relatórios (formato do evaluate). Retorna ao menos::

          {"deltas": {<mode>: {"recall@{k}": b-a, "mrr@{k}": b-a}},
           "changed_cases": [case_id, ...] (ordenado; mudou em algum modo)}

  main(argv) -> int
      CLI: ``--db PATH --out PATH --k INT`` e subcomando ``compare``.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

# --- bootstrap de sys.path (independente do import-mode do pytest) ---------
# O harness vive em scripts/benchmarks/recall_harness.py; para importá-lo como
# ``scripts.benchmarks.recall_harness`` (namespace package) precisamos da raiz
# do repositório no caminho. Adicionamos também scripts/benchmarks para o
# reuso plano de ``locomo_evaluator`` (recall_at_k / mrr).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCH_DIR = os.path.join(_REPO_ROOT, "scripts", "benchmarks")
for _p in (_REPO_ROOT, _BENCH_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# fixtures sintéticas (SQLite em tmp_path)
# ---------------------------------------------------------------------------

MEMORIES_DDL = (
    "CREATE TABLE IF NOT EXISTS memories ("
    "  content_hash TEXT PRIMARY KEY,"
    "  content      TEXT NOT NULL,"
    "  tags         TEXT,"
    "  deleted_at   TEXT"
    ")"
)


@pytest.fixture
def make_db(tmp_path):
    """Cria um banco SQLite sintético em tmp_path com a tabela ``memories``.

    ``make_db(memories)`` -> (conn, db_path). Cada memória é
    ``{"content_hash","content","tags"?,"deleted_at"?}``; ``deleted_at`` None
    significa memória viva. O INSERT do fixture é SETUP do teste (permitido) —
    a restrição R6 vale para o harness, não para o fixture.
    """

    def _make(memories, name="bench.sqlite"):
        db_path = tmp_path / name
        conn = sqlite3.connect(str(db_path))
        conn.execute(MEMORIES_DDL)
        conn.executemany(
            "INSERT INTO memories (content_hash, content, tags, deleted_at) "
            "VALUES (?, ?, ?, ?)",
            [
                (
                    m["content_hash"],
                    m["content"],
                    m.get("tags", ""),
                    m.get("deleted_at"),
                )
                for m in memories
            ],
        )
        conn.commit()
        return conn, str(db_path)

    return _make


@pytest.fixture
def write_cases_file(tmp_path):
    """Escreve um dataset no formato de eval/recall_cases.json e retorna o path."""

    def _write(cases, name="cases.json"):
        payload = {
            "version": 1,
            "created": "2026-10-17",
            "note": "synthetic test dataset",
            "k_default": 10,
            "cases": cases,
        }
        path = tmp_path / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    return _write


def _noop_runner(*args, **kwargs):
    """Runner que não retorna resultados (posições todas None)."""
    return []


# ---------------------------------------------------------------------------
# 1. test_dataset_valida_gold_terms
# ---------------------------------------------------------------------------


def test_dataset_valida_gold_terms(write_cases_file):
    """Caso sem ``gold_terms`` (vazio) é rejeitado; arquivo válido carrega."""
    from scripts.benchmarks.recall_harness import load_cases

    # (a) arquivo válido carrega e retorna os casos
    valid = [
        {"id": "a", "pergunta": "pergunta a", "categoria": "c",
         "gold_terms": ["termo-a"], "gold_hashes": ["h1"]},
        {"id": "b", "pergunta": "pergunta b", "categoria": "c",
         "gold_terms": ["termo-b"], "gold_hashes": ["h2"]},
    ]
    path_ok = write_cases_file(valid, name="ok.json")
    loaded = load_cases(path_ok)
    assert isinstance(loaded, list)
    assert [c["id"] for c in loaded] == ["a", "b"]

    # (b) caso com gold_terms VAZIO => rejeitado (ValueError)
    bad_empty = [
        {"id": "ok", "pergunta": "pergunta", "categoria": "c",
         "gold_terms": ["termo"], "gold_hashes": ["h1"]},
        {"id": "sem-terms", "pergunta": "pergunta", "categoria": "c",
         "gold_terms": [], "gold_hashes": ["h2"]},
    ]
    path_empty = write_cases_file(bad_empty, name="empty.json")
    with pytest.raises(ValueError):
        load_cases(path_empty)

    # (c) caso sem ``id`` => rejeitado (ValueError)
    bad_noid = [
        {"pergunta": "pergunta", "categoria": "c",
         "gold_terms": ["termo"], "gold_hashes": ["h1"]},
    ]
    path_noid = write_cases_file(bad_noid, name="noid.json")
    with pytest.raises(ValueError):
        load_cases(path_noid)


# ---------------------------------------------------------------------------
# 2. test_gold_term_inexistente_vira_invalid_case
# ---------------------------------------------------------------------------


def test_gold_term_inexistente_vira_invalid_case(make_db):
    """gold_term ausente no banco => invalid_case e fica FORA das métricas."""
    from scripts.benchmarks.recall_harness import evaluate, validate_cases

    conn, _ = make_db(
        [
            # memória viva contendo o termo do caso "ok"
            {"content_hash": "h1",
             "content": "decidimos parar o delta-sync entre maquinas",
             "tags": "infra", "deleted_at": None},
        ]
    )
    try:
        cases = [
            {"id": "ok", "pergunta": "quando paramos de copiar o banco",
             "categoria": "decisao", "gold_terms": ["delta-sync"]},
            {"id": "missing", "pergunta": "qual o vip do rer",
             "categoria": "infra", "gold_terms": ["10.100.0.18"]},
        ]
        validos, invalidos = validate_cases(cases, conn)

        valid_ids = sorted(c["id"] for c in validos)
        invalid_ids = sorted(c["id"] for c in invalidos)
        assert valid_ids == ["ok"]
        assert invalid_ids == ["missing"]
        # o caso invalido não vaza para a lista de válidos
        assert "missing" not in valid_ids

        # ... e fica FORA das métricas: só os validos são avaliados
        report = evaluate(validos, _noop_runner, k=10)
        all_positions = {
            cid
            for mode in report["modes"].values()
            for cid in mode["positions"]
        }
        assert "missing" not in all_positions
        assert "ok" in all_positions
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3. test_recall_e_mrr_por_modo
# ---------------------------------------------------------------------------


def test_recall_e_mrr_por_modo():
    """Posições conhecidas: acertos na posição 1 e 3 => recall@10=1.0, mrr@10=2/3.

    Deve passar APENAS com a lógica de métrica correta (falha por lógica após
    um GREEN parcial, não por import).
    """
    from scripts.benchmarks.recall_harness import evaluate

    cases = [
        {"id": "ca", "pergunta": "pergunta um", "categoria": "cat",
         "gold_terms": ["ALPHA-TERM"]},
        {"id": "cb", "pergunta": "pergunta dois", "categoria": "cat",
         "gold_terms": ["BETA-TERM"]},
    ]

    def runner(pergunta, mode, *args, **kwargs):
        # mesmo ranking controlado para os 4 modos:
        #   caso "ca" -> hit na posição 1
        #   caso "cb" -> hit na posição 3
        if pergunta == "pergunta um":
            return [
                {"content": "ALPHA-TERM presente aqui", "content_hash": "x1"},
            ]
        return [
            {"content": "ruido um", "content_hash": "x2"},
            {"content": "ruido dois", "content_hash": "x3"},
            {"content": "BETA-TERM aparece na terceira", "content_hash": "x4"},
        ]

    report = evaluate(cases, runner, k=10)

    expected_recall = 1.0              # 2/2 casos com acerto no top-10
    expected_mrr = (1.0 + 1.0 / 3.0) / 2.0  # (1/1 + 1/3) / 2 = 2/3
    for mode in ("semantic", "exact", "hybrid", "ranked"):
        m = report["modes"][mode]
        assert m["recall@10"] == pytest.approx(expected_recall), mode
        assert m["mrr@10"] == pytest.approx(expected_mrr), mode


# ---------------------------------------------------------------------------
# 4. test_posicao_por_termo_nao_por_hash
# ---------------------------------------------------------------------------


def test_posicao_por_termo_nao_por_hash():
    """Acerto pela PRIMEIRA ocorrência do termo no conteúdo (case-insensitive).

    Dois resultados contêm o termo; a posição do acerto é a primeira ocorrência
    (posição do conteúdo), não um hash fixo. Os content_hash são arbitrários e
    não correspondem a nenhum gold_hash — prova que o match é por conteúdo.
    """
    from scripts.benchmarks.recall_harness import posicao_do_acerto

    resultados = [
        {"content": "nota que não contém o termo", "content_hash": "aaaa"},
        {"content": "decidimos parar o Delta-Sync", "content_hash": "bbbb"},  # pos 2
        {"content": "ainda fala do delta-sync aqui", "content_hash": "cccc"},  # pos 3
    ]
    # case-insensitive ("Delta-Sync" casa com "delta-sync") e primeira ocorrência
    assert posicao_do_acerto(resultados, ["delta-sync"]) == 2

    # nenhum resultado contém o termo => None
    assert posicao_do_acerto(resultados, ["termo-inexistente"]) is None

    # a primeira ocorrência vence mesmo que haja várias
    resultados2 = [
        {"content": "delta-sync primeiro", "content_hash": "1"},
        {"content": "delta-sync segundo", "content_hash": "2"},
    ]
    assert posicao_do_acerto(resultados2, ["delta-sync"]) == 1


# ---------------------------------------------------------------------------
# 5. test_determinismo_saida_ordenada
# ---------------------------------------------------------------------------


def test_determinismo_saida_ordenada():
    """Duas execuções com a mesma entrada => JSON idêntico (CA2)."""
    from scripts.benchmarks.recall_harness import evaluate

    cases = [
        {"id": "zeta", "pergunta": "p1", "categoria": "c1", "gold_terms": ["T1"]},
        {"id": "alpha", "pergunta": "p2", "categoria": "c2", "gold_terms": ["T2"]},
        {"id": "mid", "pergunta": "p3", "categoria": "c1", "gold_terms": ["T3"]},
    ]

    def runner(pergunta, mode, *args, **kwargs):
        # ranking determinístico derivado da pergunta
        if pergunta == "p1":
            return [{"content": "T1 aqui", "content_hash": "h1"}]
        if pergunta == "p2":
            return [
                {"content": "ruido", "content_hash": "h2"},
                {"content": "T2 aqui", "content_hash": "h3"},
            ]
        return [{"content": "T3 aqui", "content_hash": "h4"}]

    r1 = evaluate(cases, runner, k=10)
    r2 = evaluate(cases, runner, k=10)

    # estrutura idêntica entre execuções
    assert r1 == r2

    # serialização canônica (chaves ordenadas) => bytes idênticos
    s1 = json.dumps(r1, sort_keys=True, ensure_ascii=False)
    s2 = json.dumps(r2, sort_keys=True, ensure_ascii=False)
    assert s1 == s2

    # "estável ordenado": posições por modo têm chaves ordenadas
    for mode in r1["modes"].values():
        keys = list(mode["positions"].keys())
        assert keys == sorted(keys), f"positions não ordenadas em {mode}"


# ---------------------------------------------------------------------------
# 6. test_nenhuma_escrita
# ---------------------------------------------------------------------------


class _NoopCursor:
    """Cursor inofensivo para quando uma escrita for interceptada (não executada)."""

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def __iter__(self):
        return iter([])

    def close(self):
        return None


class _SpyConnection:
    """Proxy de sqlite3.Connection que REGISTRA o SQL e bloqueia escritas.

    Leitura (SELECT/...) -> encaminhado ao conn real.
    Escrita (INSERT/UPDATE/DELETE/REPLACE/CREATE/DROP/ALTER/VACUUM) ->
    registrada em ``writes`` e NÃO executada (retorna um cursor no-op).
    ``commit()``/``__exit__`` são contados, nunca encaminhados.
    """

    _WRITE = {"insert", "update", "delete", "replace", "create", "drop",
              "alter", "vacuum"}

    def __init__(self, real):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "statements", [])
        object.__setattr__(self, "writes", [])
        object.__setattr__(self, "commits", 0)

    def _head(self, sql):
        s = (sql or "").strip()
        return s.split(None, 1)[0].lower() if s else ""

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)
        if self._head(sql) in self._WRITE:
            self.writes.append(sql)
            return _NoopCursor()
        return self._real.execute(sql, *args, **kwargs)

    def executemany(self, sql, *args, **kwargs):
        self.statements.append(sql)
        if self._head(sql) in self._WRITE:
            self.writes.append(sql)
            return _NoopCursor()
        return self._real.executemany(sql, *args, **kwargs)

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # não faz auto-commit encoberto
        return False

    def cursor(self):
        return self._real.cursor()

    def close(self):
        return self._real.close()

    def __getattr__(self, name):
        # row_factory, in_transaction, etc. -> conn real
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name, value):
        if name in ("_real", "statements", "writes", "commits"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_real"), name, value)


def test_nenhuma_escrita(make_db):
    """O harness nunca emite INSERT/UPDATE/DELETE nem commit (R6/CA5)."""
    from scripts.benchmarks.recall_harness import validate_cases

    conn, _ = make_db(
        [
            {"content_hash": "h1",
             "content": "o delta-sync foi aposentado",
             "tags": "infra", "deleted_at": None},
        ]
    )
    spy = _SpyConnection(conn)
    cases = [
        {"id": "ok", "pergunta": "quando aposentar o delta-sync",
         "categoria": "decisao", "gold_terms": ["delta-sync"]},
    ]
    try:
        validos, invalidos = validate_cases(cases, spy)
        # o caso válido deve ter sido classificado (a validação rodou)
        assert [c["id"] for c in validos] == ["ok"]

        # a validação DEVE ter feito ao menos uma leitura (caso contrário o
        # teste seria vazio): alguma SELECT registrada
        assert any(
            (s or "").strip().lower().startswith("select")
            for s in spy.statements
        ), "a validação não consultou o banco (spy sem SELECT)"

        # NENHUMA escrita e NENHUM commit pelo harness
        assert spy.writes == []
        assert spy.commits == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 7. test_compare_deltas
# ---------------------------------------------------------------------------


def test_compare_deltas():
    """compare() => deltas corretos (b-a) e casos que mudaram de posição."""
    from scripts.benchmarks.recall_harness import compare

    def _report(rec_sem, mrr_sem, rec_ex, mrr_ex, pos_sem, pos_ex):
        return {
            "meta": {"k": 10},
            "modes": {
                "semantic": {
                    "recall@10": rec_sem, "mrr@10": mrr_sem,
                    "positions": pos_sem,
                },
                "exact": {
                    "recall@10": rec_ex, "mrr@10": mrr_ex,
                    "positions": pos_ex,
                },
            },
            "invalid_cases": [],
        }

    # A (antes) vs B (depois):
    #   c1: 1 -> 1 (inalterado)          c4: 2 -> 2 (inalterado)
    #   c2: 4 -> 2 (mudou em semantic)   c3: None -> 3 (mudou em semantic)
    report_a = _report(
        rec_sem=0.5, mrr_sem=0.3, rec_ex=0.5, mrr_ex=0.3,
        pos_sem={"c1": 1, "c2": 4, "c3": None, "c4": 2},
        pos_ex={"c1": 1, "c2": 4, "c3": None, "c4": 2},
    )
    report_b = _report(
        rec_sem=0.75, mrr_sem=0.5, rec_ex=0.5, mrr_ex=0.3,
        pos_sem={"c1": 1, "c2": 2, "c3": 3, "c4": 2},
        pos_ex={"c1": 1, "c2": 4, "c3": None, "c4": 2},
    )

    res = compare(report_a, report_b)

    # deltas (B - A) por modo
    assert res["deltas"]["semantic"]["recall@10"] == pytest.approx(0.25)
    assert res["deltas"]["semantic"]["mrr@10"] == pytest.approx(0.20)
    assert res["deltas"]["exact"]["recall@10"] == pytest.approx(0.0)
    assert res["deltas"]["exact"]["mrr@10"] == pytest.approx(0.0)

    # casos que mudaram de posição (em algum modo), ordenado
    assert res["changed_cases"] == ["c2", "c3"]
