"""Negation minimal pairs (mantenedor, PR #1696) contra o NOSSO rerank (#1602).

Mesma construção de corpus do benchmark do upstream:
  50 pares (pos/neg) + 15 distratores = 115 memórias em sqlite-vec isolado.
Mesmas métricas: pairwise accuracy (o membro certo ranqueia acima do outro),
recortada por estilo (explicit / implicit), mais top-1 e latência.

Condições medidas:
  cosine      -- baseline de similaridade sobre TODAS as linhas (exato)
  rerank40    -- nosso estágio: cross-encoder sobre os 40 melhores por cosseno
  rerank_all  -- teto: cross-encoder sobre o corpus inteiro (115)

Honestidade embutida: reporta quantos pares têm AMBOS os membros dentro do
pool de candidatos. Fora do pool, o rerank não pode reordenar nada.
"""

import asyncio
import hashlib
import json
import math
import os
import shutil
import statistics
import sys
import tempfile
import time
from collections import defaultdict

MODEL = os.environ.get("BENCH_EMBED_MODEL", "all-MiniLM-L6-v2")
os.environ["MCP_EMBEDDING_MODEL"] = MODEL
os.environ["MCP_RERANK_ENABLED"] = "true"
os.environ["MCP_RERANK_CANDIDATES"] = "40"
os.environ["MCP_RERANK_MODEL"] = "Xenova/bge-reranker-base"
os.environ["MCP_NLI_ON_STORE"] = "false"

sys.path.insert(0, "/home/claudio/git/mms/mms/src")

from mcp_memory_service.models.memory import Memory  # noqa: E402
from mcp_memory_service.quality.search_rerank import (  # noqa: E402
    SearchRerankConfig,
    rerank_candidates,
)
from mcp_memory_service.storage.mixins.base import deserialize_embedding  # noqa: E402
from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "negation_pairs.json"), encoding="utf-8"))

CANDIDATES_SQL = """
    SELECT m.content_hash, m.content, e.content_embedding
    FROM memories m
    JOIN memory_embeddings e ON m.id = e.rowid
    WHERE m.deleted_at IS NULL
      AND (m.embedding_pending IS NULL OR m.embedding_pending = 0)
      AND (m.superseded_by IS NULL OR m.superseded_by = '')
"""


def cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def store(storage, content, tags):
    m = Memory(content=content, content_hash=hashlib.sha256(content.encode()).hexdigest(), tags=tags)
    ok, msg = await storage.store(m, skip_semantic_dedup=True)
    if not ok:
        raise RuntimeError(f"store failed: {msg}")
    return m.content_hash


def mean(v):
    return statistics.fmean(v) if v else float("nan")


async def main():
    tmp = tempfile.mkdtemp(prefix="neg-rerank-")
    storage = SqliteVecMemoryStorage(os.path.join(tmp, "memories.db"))
    await storage.initialize()
    if getattr(storage, "embedding_backend_degraded", False):
        raise RuntimeError("embedding model unavailable (hash fallback)")
    try:
        members = {}
        for pair in DATA["pairs"]:
            members[pair["id"]] = (
                await store(storage, pair["pos"], ["neg-bench", f"pair:{pair['id']}", "pos"]),
                await store(storage, pair["neg"], ["neg-bench", f"pair:{pair['id']}", "neg"]),
            )
        for i, text in enumerate(DATA["distractors"]):
            await store(storage, text, ["neg-bench", f"distractor:{i}"])

        rows = storage.conn.execute(CANDIDATES_SQL).fetchall()
        vectors, contents = {}, {}
        for h, c, blob in rows:
            v = deserialize_embedding(blob)
            if v is not None:
                vectors[h] = v
                contents[h] = c
        n = len(vectors)
        print(f"modelo={MODEL}  armazenadas={n}  dim={storage.embedding_dimension}")

        config = SearchRerankConfig.from_env()
        print(f"rerank: enabled={config.enabled} candidates={config.candidates} model={config.model}\n")

        async def ranking(query, pool_size):
            qv = storage._generate_embedding(query)
            order = sorted(((h, cos(qv, v)) for h, v in vectors.items()), key=lambda t: t[1], reverse=True)
            if pool_size is None:
                return [h for h, _ in order], 0.0, None
            pool = order[:pool_size]
            cands = [{"content": contents[h], "content_hash": h} for h, _ in pool]
            t0 = time.perf_counter()
            ordered = await rerank_candidates(query, cands, config)
            dt = (time.perf_counter() - t0) * 1000
            if ordered is None:
                raise RuntimeError("rerank failed (fail-open) -- resultado nao seria comparavel")
            head = [m["content_hash"] for m in ordered]
            tail = [h for h, _ in order[pool_size:]]
            return head + tail, dt, {h for h, _ in pool}

        async def score(pool_size):
            hits = defaultdict(list)
            lat = []
            in_pool = 0
            for pair in DATA["pairs"]:
                pos_h, neg_h = members[pair["id"]]
                for query, want, other, key in (
                    (pair["q_pos"], pos_h, neg_h, "pos"),
                    (pair["q_neg"], neg_h, pos_h, "neg"),
                ):
                    ranked, dt, pool = await ranking(query, pool_size)
                    lat.append(dt)
                    rw = ranked.index(want) if want in ranked else n
                    ro = ranked.index(other) if other in ranked else n
                    hits[key].append(float(rw < ro))
                    hits[f"{key}_{pair.get('style', 'explicit')}"].append(float(rw < ro))
                    hits[f"top1_{key}"].append(float(ranked[:1] == [want]))
                    if pool_size is not None:
                        top = set(ranked[:pool])
                        if want in top and other in top:
                            in_pool += 1
            return {
                "pairwise_all": mean(hits["pos"] + hits["neg"]),
                "pos": mean(hits["pos"]),
                "neg": mean(hits["neg"]),
                "neg_explicit": mean(hits["neg_explicit"]),
                "neg_implicit": mean(hits["neg_implicit"]),
                "top1_pos": mean(hits["top1_pos"]),
                "top1_neg": mean(hits["top1_neg"]),
                "pares_no_pool": f"{in_pool}/100" if pool_size is not None else "100/100",
                "p50_ms": round(statistics.median(lat), 1) if pool_size is not None else 0.0,
            }

        per_query = {}

        async def score_keep(name, pool_size):
            hits = defaultdict(list)
            lat = []
            pairs_in_pool = 0
            order = []
            for pair in DATA["pairs"]:
                pos_h, neg_h = members[pair["id"]]
                for query, want, other, key in (
                    (pair["q_pos"], pos_h, neg_h, "pos"),
                    (pair["q_neg"], neg_h, pos_h, "neg"),
                ):
                    ranked, dt, pool = await ranking(query, pool_size)
                    lat.append(dt)
                    rw = ranked.index(want) if want in ranked else n
                    ro = ranked.index(other) if other in ranked else n
                    hits[key].append(float(rw < ro))
                    hits[f"{key}_{pair.get('style', 'explicit')}"].append(float(rw < ro))
                    hits[f"top1_{key}"].append(float(ranked[:1] == [want]))
                    if pool is not None and want in pool and other in pool:
                        pairs_in_pool += 1
            # ordem estável: 50 pares x (q_pos, q_neg)
            order = [hits["pos"][i] for i in range(len(hits["pos"]))]
            neg_order = hits["neg"]
            per_query[name] = [v for pair in zip(order, neg_order) for v in pair]
            return {
                "pairwise_all": mean(hits["pos"] + hits["neg"]),
                "pos": mean(hits["pos"]),
                "neg": mean(hits["neg"]),
                "neg_explicit": mean(hits["neg_explicit"]),
                "neg_implicit": mean(hits["neg_implicit"]),
                "top1_pos": mean(hits["top1_pos"]),
                "top1_neg": mean(hits["top1_neg"]),
                "pares_no_pool": f"{pairs_in_pool}/100" if pool_size is not None else "100/100",
                "p50_ms": round(statistics.median(lat), 1) if pool_size is not None else 0.0,
            }

        results = {
            "cosine": await score_keep("cosine", None),
            "rerank40": await score_keep("rerank40", 40),
            "rerank_all": await score_keep("rerank_all", n),
        }
        _ = score

        cols = ["pairwise_all", "pos", "neg", "neg_explicit", "neg_implicit",
                "top1_pos", "top1_neg", "pares_no_pool", "p50_ms"]
        print("| condição | " + " | ".join(cols) + " |")
        print("|---" * (len(cols) + 1) + "|")
        for name, r in results.items():
            print(f"| {name} | " + " | ".join(str(r[c]) for c in cols) + " |")
        # ---- bootstrap pareado nas decisões por consulta (100 consultas) ----
        import random
        rng = random.Random(20261026)

        def paired_bootstrap(a, b, resamples=10000):
            deltas = [y - x for x, y in zip(a, b)]
            m = len(deltas)
            means = []
            for _ in range(resamples):
                s = sum(deltas[rng.randrange(m)] for _ in range(m))
                means.append(s / m)
            means.sort()
            lo = means[int(0.025 * resamples)]
            hi = means[int(0.975 * resamples) - 1]
            return mean(deltas), lo, hi, sum(1 for d in deltas if d > 0), sum(1 for d in deltas if d < 0)

        print("\nbootstrap pareado (10.000 reamostragens sobre 100 consultas):")
        boot = {}
        for name in ("rerank40", "rerank_all"):
            d, lo, hi, imp, wor = paired_bootstrap(per_query["cosine"], per_query[name])
            boot[name] = {"delta": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)],
                          "melhorou": imp, "piorou": wor}
            print(f"  cosine -> {name}: delta {d*100:+.1f} p.p.  IC95 [{lo*100:+.1f}, {hi*100:+.1f}]  "
                  f"consultas melhoraram={imp} pioraram={wor}")
        results["bootstrap"] = boot

        json.dump(results, open(os.path.join(os.path.dirname(__file__), f"resultado_{MODEL}.json"), "w"), indent=1)
    finally:
        await storage.close()
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(main())
