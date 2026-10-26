"""Verificação do pool: quantos pares têm AMBOS os membros no top-40 do cosseno.

Sem isso, 'pares_no_pool = 100/100' seria afirmação sem prova. Mede as posições
reais dos dois membros de cada par sob cosseno e o máximo entre elas.
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

MODEL = os.environ.get("BENCH_EMBED_MODEL", "all-MiniLM-L6-v2")
os.environ["MCP_EMBEDDING_MODEL"] = MODEL
os.environ["MCP_NLI_ON_STORE"] = "false"
sys.path.insert(0, "/home/claudio/git/mms/mms/src")

from mcp_memory_service.models.memory import Memory  # noqa: E402
from mcp_memory_service.storage.mixins.base import deserialize_embedding  # noqa: E402
from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage  # noqa: E402

DATA = json.load(open(os.path.join(os.path.dirname(__file__), "negation_pairs.json"), encoding="utf-8"))
SQL = """SELECT m.content_hash, e.content_embedding FROM memories m
JOIN memory_embeddings e ON m.id = e.rowid
WHERE m.deleted_at IS NULL AND (m.embedding_pending IS NULL OR m.embedding_pending=0)
AND (m.superseded_by IS NULL OR m.superseded_by='')"""


def cos(a, b):
    d = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return d / (na * nb) if na and nb else 0.0


async def main():
    tmp = tempfile.mkdtemp(prefix="neg-pool-")
    st = SqliteVecMemoryStorage(os.path.join(tmp, "m.db"))
    await st.initialize()
    try:
        members = {}
        for pair in DATA["pairs"]:
            hs = []
            for text in (pair["pos"], pair["neg"]):
                m = Memory(content=text, content_hash=hashlib.sha256(text.encode()).hexdigest(), tags=["bench"])
                ok, msg = await st.store(m, skip_semantic_dedup=True)
                if not ok:
                    raise RuntimeError(msg)
                hs.append(m.content_hash)
            members[pair["id"]] = tuple(hs)
        for text in DATA["distractors"]:
            m = Memory(content=text, content_hash=hashlib.sha256(text.encode()).hexdigest(), tags=["bench"])
            await st.store(m, skip_semantic_dedup=True)
        vecs = {h: deserialize_embedding(b) for h, b in st.conn.execute(SQL).fetchall()}
        n = len(vecs)
        maxranks = []
        for pair in DATA["pairs"]:
            pos, neg = members[pair["id"]]
            for q in (pair["q_pos"], pair["q_neg"]):
                qv = st._generate_embedding(q)
                order = sorted(((h, cos(qv, v)) for h, v in vecs.items()), key=lambda t: t[1], reverse=True)
                idx = {h: i for i, (h, _) in enumerate(order)}
                maxranks.append(max(idx[pos], idx[neg]) + 1)
        print(f"modelo={MODEL}  n={n}")
        print(f"consultas={len(maxranks)}  max(posto_pos,posto_neg): "
              f"mediana={statistics.median(maxranks)}  p90={sorted(maxranks)[int(0.9*len(maxranks))-1]}  "
              f"máximo={max(maxranks)}")
        for k in (10, 20, 40, 60):
            dentro = sum(1 for r in maxranks if r <= k)
            print(f"  ambos no top-{k}: {dentro}/{len(maxranks)}")
    finally:
        await st.close()
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(main())
