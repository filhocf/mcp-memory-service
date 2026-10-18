"""Testes RED do experimento A/B de modelos de embedding (scripts/benchmarks/model_ab.py).

Diferente do harness de ``memory_search`` (``recall_harness.py``), este harness é
independente do storage: embute o corpus e as queries com cada modelo ONNX local
e mede recall/MRR por similaridade de cosseno, sem tocar no sqlite-vec.

Estes testes fixam o contrato público e, como o módulo não existe ainda, DEVEM
FALHAR agora (erro de import). Após o GREEN, cada teste deve passar por LÓGICA.

Isolamento:
  * SQLite sintético em ``tmp_path`` (tabela ``memories``) — nada toca o acervo real.
  * embedding testado com ``_build_session``/``_build_tokenizer`` monkeypatchados
    (fakes), sem carregar os ONNX reais de centenas de MB nos testes de unidade.
  * sem skip/xfail.

CONTRATO PÚBLICO (a ser honrado por scripts/benchmarks/model_ab.py):

  load_corpus(db_path) -> list[tuple[str, str]]
      (content_hash, content) de cada memória viva (``deleted_at IS NULL``) e de
      conteúdo não vazio, em ordem determinística (rowid). Conexão ``mode=ro``.

  load_cases(path) -> list[dict]
      Reusa o formato de ``eval/recall_cases.json`` (objeto com chave ``cases``).
      VALIDA ``id``, ``pergunta`` e ``gold_terms``/``gold_hashes``.

  embed_texts(onnx_dir, texts, batch=16, max_len=256, prefix='') -> np.ndarray
      (n, dim) — mean pooling + L2 normalize. Escolhe o ``.onnx`` em ``onnx/``
      ou na raiz; usa onnxruntime + tokenizers; ``prefix`` anteposto a cada texto.

  topk_positions(corpus_emb, query_emb, k) -> list[int]
      Índices (0-based) dos ``k`` documentos de maior similaridade de cosseno.

  recall_mrr(positions, corpus_hashes, cases, k=10) -> dict
      ``{"recall@{k}", "mrr@{k}", "casos": {case_id: pos|None}}``. Acerto =
      ``gold_hash`` do caso presente no top-k (posição 1-based do primeiro).

  main(argv) -> int
      CLI: ``--db`` ``--cases`` ``--model nome=dir[,prefixo=Q/P]`` ``--out`` ``--k``.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import numpy as np
import pytest

# --- bootstrap de sys.path (independente do import-mode do pytest) ----------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BENCH_DIR = os.path.join(_REPO_ROOT, "scripts", "benchmarks")
for _p in (_REPO_ROOT, _BENCH_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# 1. test_topk_positions — ordem conhecida de similaridade de cosseno
# ---------------------------------------------------------------------------


def test_topk_positions():
    """Vetores sintéticos com cossenos distintos => ordem determinística."""
    from scripts.benchmarks.model_ab import topk_positions

    # cossenos de cada doc contra a query [1,0]:
    #   doc0 [1,0]     -> 1.0
    #   doc1 [0.9,~0.436] -> 0.9
    #   doc2 [0.5,~0.866] -> 0.5
    #   doc3 [0,1]     -> 0.0
    corpus = np.array(
        [
            [1.0, 0.0],
            [0.9, 0.43589],
            [0.5, 0.86603],
            [0.0, 1.0],
        ]
    )
    query = np.array([1.0, 0.0])

    assert topk_positions(corpus, query, 3) == [0, 1, 2]
    assert topk_positions(corpus, query, 1) == [0]
    assert topk_positions(corpus, query, 4) == [0, 1, 2, 3]

    # k maior que o corpus => devolve todos, sem erro
    assert sorted(topk_positions(corpus, query, 99)) == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# 2. test_recall_mrr — gabarito controlado (acertos nas posições 1 e 3)
# ---------------------------------------------------------------------------


def test_recall_mrr():
    """Acertos na posição 1 (caso ca) e na posição 3 (caso cb) => recall 1.0, mrr 2/3."""
    from scripts.benchmarks.model_ab import recall_mrr

    corpus_hashes = ["h0", "h1", "h2", "h3", "h4"]
    # ca: gold_hash h0 está no idx0 do corpus, que é o 1º de ca  -> posição 1
    # cb: gold_hash h1 está no idx1 do corpus, que é o 3º de cb  -> posição 3
    positions = {
        "ca": [0, 1, 2, 3, 4],
        "cb": [3, 4, 1, 2, 0],
    }
    cases = [
        {"id": "ca", "pergunta": "p1", "gold_terms": ["x"], "gold_hashes": ["h0"]},
        {"id": "cb", "pergunta": "p2", "gold_terms": ["y"], "gold_hashes": ["h1"]},
    ]

    res = recall_mrr(positions, corpus_hashes, cases, k=10)

    assert res["recall@10"] == pytest.approx(1.0)  # 2/2 casos com acerto no top-10
    assert res["mrr@10"] == pytest.approx((1.0 + 1.0 / 3.0) / 2.0)  # (1/1 + 1/3)/2
    assert res["casos"]["ca"] == 1
    assert res["casos"]["cb"] == 3


def test_recall_mrr_miss_fora_do_topk():
    """Acerto além do top-k conta como MISS (recall 0 para aquele caso)."""
    from scripts.benchmarks.model_ab import recall_mrr

    corpus_hashes = [f"h{i}" for i in range(5)]
    # só um caso: gold_hash h4 só aparece na posição 5 -> com k=3 é miss
    positions = {"c": [0, 1, 2, 3, 4]}
    cases = [
        {"id": "c", "pergunta": "p", "gold_terms": ["z"], "gold_hashes": ["h4"]},
    ]

    res = recall_mrr(positions, corpus_hashes, cases, k=3)
    assert res["recall@3"] == pytest.approx(0.0)
    assert res["mrr@3"] == pytest.approx(0.0)
    assert res["casos"]["c"] is None

    # e com k=5 vira acerto na posição 5
    res5 = recall_mrr(positions, corpus_hashes, cases, k=5)
    assert res5["recall@5"] == pytest.approx(1.0)
    assert res5["casos"]["c"] == 5


# ---------------------------------------------------------------------------
# 3. test_prefixo_aplicado — o tokenizer vê 'query: ' quando prefixo é dado
# ---------------------------------------------------------------------------


class _FakeEnc:
    """Um 'encoding' mínimo com as atribuições usadas pelo loader."""

    def __init__(self):
        self.ids = [101, 20, 102]
        self.attention_mask = [1, 1, 1]
        self.type_ids = [0, 0, 0]


class _RecordingTokenizer:
    """Fake que REGISTRA o lote de strings recebido em ``encode_batch``."""

    def __init__(self, records):
        self._records = records

    def encode_batch(self, texts):
        self._records.append(list(texts))
        return [_FakeEnc() for _ in texts]


class _FakeSession:
    """Fake de ort.InferenceSession: declara inputs e devolve um tensor de uns."""

    def __init__(self, dim=8, input_names=("input_ids", "attention_mask")):
        self._dim = dim
        self._input_names = list(input_names)

    def get_inputs(self):
        class _Input:
            def __init__(self, name):
                self.name = name

        return [_Input(n) for n in self._input_names]

    def run(self, outputs, ort_inputs):
        batch, seq = ort_inputs["input_ids"].shape
        return [np.ones((batch, seq, self._dim), dtype=np.float32)]


def test_prefixo_aplicado(monkeypatch):
    """embed_texts antepõe o prefixo: o tokenizer recebe 'query: <texto>'."""
    from scripts.benchmarks import model_ab

    records: list[list[str]] = []
    monkeypatch.setattr(model_ab, "_build_session", lambda _d: _FakeSession())
    monkeypatch.setattr(
        model_ab, "_build_tokenizer", lambda _d: _RecordingTokenizer(records)
    )

    out = model_ab.embed_texts(
        "/nao-existe", ["hello"], batch=16, max_len=256, prefix="query: "
    )

    # o tokenizer viu o texto com o prefixo anteposto
    assert records and "query: hello" in records[0]
    # e SEM prefixo o texto passa intacto
    records.clear()
    model_ab.embed_texts("/nao-existe", ["hello"], batch=16, max_len=256, prefix="")
    assert records and "hello" in records[0]
    assert "query: hello" not in records[0]

    # saída: (n, dim) de float, e vetores unitários (L2)
    assert out.shape == (1, 8)
    assert float(np.linalg.norm(out[0])) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. test_corpus_readonly — abre o DB em mode=ro; escrita deve falhar
# ---------------------------------------------------------------------------


def test_corpus_readonly(tmp_path, monkeypatch):
    """load_corpus lê do snapshot em mode=ro e retorna só memórias vivas não vazias."""
    from scripts.benchmarks import model_ab

    db_path = tmp_path / "ro.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE memories ("
        "  content_hash TEXT PRIMARY KEY,"
        "  content      TEXT NOT NULL,"
        "  store        TEXT DEFAULT 'default',"
        "  deleted_at   TEXT"
        ")"
    )
    conn.executemany(
        "INSERT INTO memories (content_hash, content, deleted_at) VALUES (?, ?, ?)",
        [
            ("h1", "viva", None),
            ("h2", "sumida", "2026-01-01T00:00:00Z"),  # apagada -> excluída
            ("h3", "   ", None),  # conteúdo vazio (só espaços) -> excluída
            ("h4", "também viva", None),
        ],
    )
    conn.commit()
    conn.close()

    real_connect = sqlite3.connect
    captured: dict = {}

    def spy_connect(*args, **kwargs):
        url = args[0] if args else kwargs.get("database")
        captured["url"] = url
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spy_connect)
    rows = model_ab.load_corpus(str(db_path))

    # só as memórias vivas de conteúdo não vazio, em ordem de rowid
    assert [h for h, _ in rows] == ["h1", "h4"]
    assert dict(rows) == {"h1": "viva", "h4": "também viva"}

    # a conexão foi aberta em modo somente-leitura
    assert captured.get("url", "").startswith("file:")
    assert "mode=ro" in captured["url"]

    # prova da garantia: uma conexão mode=ro ao mesmo arquivo RECUSA escrita
    ro = real_connect("file:" + str(db_path) + "?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute(
                "INSERT INTO memories (content_hash, content, deleted_at) "
                "VALUES ('zz', 'zz', NULL)"
            )
    finally:
        ro.close()


# ---------------------------------------------------------------------------
# 5. test_normalizacao_l2 — vetores unitários
# ---------------------------------------------------------------------------


def test_normalizacao_l2():
    """_l2_normalize devolve vetores unitários; vetor zero => zero (sem NaN)."""
    from scripts.benchmarks.model_ab import _l2_normalize

    v = np.array([[3.0, 4.0], [0.0, 0.0], [1.0, 1.0]])
    out = _l2_normalize(v)

    norms = np.linalg.norm(out, axis=1)
    assert norms[0] == pytest.approx(1.0)
    assert norms[1] == pytest.approx(0.0)  # vetor zero não vira NaN
    assert norms[2] == pytest.approx(1.0)

    # direção preservada: [3,4] -> [0.6, 0.8]
    assert out[0, 0] == pytest.approx(0.6)
    assert out[0, 1] == pytest.approx(0.8)
    assert not np.isnan(out).any()
