#!/usr/bin/env python3
"""EXP-1602/F5 — origem do RSS e do custo: max_len x batch no cross-encoder.

Replica o caminho do servico (quality/onnx_ranker._score_cross_encoder_batch)
e mede RSS (peak HWM e delta) + p50 por par para cada combinacao.
Le textos reais do acervo, modo read-only.
"""
import json
import os
import resource
import sqlite3
import statistics
import sys
import time

import numpy as np

MODEL_DIR = os.path.expanduser(
    "~/.cache/huggingface/hub/models--Xenova--bge-reranker-base/snapshots/"
    "280bcc27a84e0b898c251e06fddb25171bd9b101"
)
ONNX = os.path.join(MODEL_DIR, "onnx", "model_int8.onnx")
TOK = os.path.join(MODEL_DIR, "tokenizer.json")
DB = os.path.expanduser("~/local-data/mcp/sqlite_vec.db")


def rss_mb():
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def hwm_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def carregar_pares(n=40):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select content from memories where deleted_at is null "
        "and content is not null and length(content) > 400 "
        "order by rowid desc limit ?", (n,)
    ).fetchall()
    con.close()
    conteudos = [r[0] for r in rows]
    query = "como fazer deploy do orc na VPS"
    return [(query, c) for c in conteudos]


def main():
    import onnxruntime as ort
    from tokenizers import Tokenizer

    pares = carregar_pares(40)
    print(f"pares={len(pares)} chars_medios={int(statistics.mean(len(c) for _, c in pares))}")

    antes_load = rss_mb()
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 16
    sess = ort.InferenceSession(ONNX, sess_options=opts,
                                providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(TOK)
    tok.enable_truncation(max_length=512)
    tok.no_padding()
    depois_load = rss_mb()
    print(f"rss_antes_load={antes_load:.0f}MB rss_apos_load={depois_load:.0f}MB "
          f"delta_load={depois_load-antes_load:.0f}MB")
    print("inputs:", [i.name for i in sess.get_inputs()])

    resultados = []
    for max_len, batch in [(512, 32), (512, 8), (256, 32), (256, 8), (128, 8)]:
        # RSS de partida desta config (HWM e cumulativo, use delta)
        tok.enable_truncation(max_length=max_len)
        tempos, scores = [], []
        rss_cfg_ini = rss_mb()
        for i in range(0, len(pares), batch):
            lote = pares[i:i + batch]
            t0 = time.perf_counter()
            enc = tok.encode_batch([list(p) for p in lote])
            ml = max(len(e.ids) for e in enc)
            b = len(lote)
            ids = np.zeros((b, ml), dtype=np.int64)
            am = np.zeros((b, ml), dtype=np.int64)
            tt = np.zeros((b, ml), dtype=np.int64)
            for k, e in enumerate(enc):
                L = len(e.ids)
                ids[k, :L] = e.ids
                am[k, :L] = e.attention_mask
                tt[k, :L] = e.type_ids
            feeds = {"input_ids": ids, "attention_mask": am}
            if "token_type_ids" in [x.name for x in sess.get_inputs()]:
                feeds["token_type_ids"] = tt
            out = sess.run(None, feeds)[0].reshape(-1)
            scores.extend(out.tolist())
            tempos.append((time.perf_counter() - t0) / b * 1000)
        rss_cfg_fim = rss_mb()
        resultados.append({
            "max_len": max_len, "batch": batch,
            "ms_por_par_p50": round(statistics.median(tempos), 1),
            "ms_total": round(sum(tempos) * len(pares) / 1000, 2),
            "rss_delta_mb": round(rss_cfg_fim - rss_cfg_ini, 0),
            "rss_hwm_mb": round(hwm_mb(), 0),
        })
        print(resultados[-1], flush=True)

    # qualidade: comparar ordenacao 512x32 vs 256x8
    def ordenar(cfg):
        tok.enable_truncation(max_length=cfg[0])
        s = []
        for i in range(0, len(pares), cfg[1]):
            lote = pares[i:i + cfg[1]]
            enc = tok.encode_batch([list(p) for p in lote])
            ml = max(len(e.ids) for e in enc)
            b = len(lote)
            ids = np.zeros((b, ml), dtype=np.int64)
            am = np.zeros((b, ml), dtype=np.int64)
            tt = np.zeros((b, ml), dtype=np.int64)
            for k, e in enumerate(enc):
                L = len(e.ids)
                ids[k, :L] = e.ids
                am[k, :L] = e.attention_mask
                tt[k, :L] = e.type_ids
            feeds = {"input_ids": ids, "attention_mask": am}
            if "token_type_ids" in [x.name for x in sess.get_inputs()]:
                feeds["token_type_ids"] = tt
            s.extend(sess.run(None, feeds)[0].reshape(-1).tolist())
        return s

    s512 = ordenar((512, 32))
    s256 = ordenar((256, 8))
    top10_512 = set(np.argsort(s512)[-10:].tolist())
    top10_256 = set(np.argsort(s256)[-10:].tolist())
    print(f"top10_igual_512_vs_256={top10_512 == top10_256} "
          f"interseccao={len(top10_512 & top10_256)}/10")

    saida = os.path.expanduser("~/git/mms/lab-recall/eval/lab_rerank_rss_shape.json")
    json.dump({"pares": len(pares), "resultados": resultados,
               "top10_igual_512_vs_256_40pares": top10_512 == top10_256},
              open(saida, "w"), indent=2)
    print("artefato:", saida)


if __name__ == "__main__":
    main()
