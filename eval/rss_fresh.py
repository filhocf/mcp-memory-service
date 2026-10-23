#!/usr/bin/env python3
"""EXP-1602/F5v2 — RSS por config em PROCESSO FRESCO.

Corrige o defeito do teste anterior: medir varias configs no mesmo processo
esconde a arena ja retida pela primeira config (a ordem vira resultado).
Aqui: um subprocesso por (seq, batch), com o NUMERO DE LOTES do servico
(120 consultas x 2 lotes de 32 e 8 = 240 lotes) e RSS lido de /proc.

Uso: python3 rss_fresh.py            # roda a matriz
     python3 rss_fresh.py 512 32     # roda so uma config (modo worker)
"""
import json
import os
import sqlite3
import statistics
import subprocess
import sys

DB = os.path.expanduser("~/local-data/mcp/sqlite_vec.db")
MODEL_DIR = os.path.expanduser(
    "~/.cache/huggingface/hub/models--Xenova--bge-reranker-base/snapshots/"
    "280bcc27a84e0b898c251e06fddb25171bd9b101"
)
ONNX = os.path.join(MODEL_DIR, "onnx", "model_int8.onnx")
TOK = os.path.join(MODEL_DIR, "tokenizer.json")


def pares(n=40):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "select content from memories where deleted_at is null and content is not null "
        "and length(content) > 400 order by rowid desc limit ?", (n,)).fetchall()
    con.close()
    q = "como fazer deploy do orc na VPS"
    return [(q, r[0]) for r in rows]


def rss_mb(pid=None):
    if pid is None:
        pid = os.getpid()
    with open(f"/proc/{pid}/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return 0.0


def worker(max_len, batch, lotes):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    ps = pares(40)
    base = rss_mb()
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.environ.get("MCP_ORT_THREADS", "0") or 0)
    sess = ort.InferenceSession(ONNX, sess_options=opts, providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(TOK)
    tok.enable_truncation(max_length=max_len)
    tok.no_padding()
    pos_load = rss_mb()
    tempos = []
    import time
    for r in range(lotes):
        for i in range(0, len(ps), batch):
            lote = ps[i:i + batch]
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
            sess.run(None, feeds)
            tempos.append((time.perf_counter() - t0) / b * 1000)
    print(json.dumps({
        "max_len": max_len, "batch": batch, "lotes": lotes,
        "rss_base_mb": round(base), "rss_pos_load_mb": round(pos_load),
        "delta_load_mb": round(pos_load - base),
        "delta_infer_mb": round(rss_mb() - pos_load),
        "rss_final_mb": round(rss_mb()),
        "ms_por_par_p50": round(statistics.median(tempos), 1),
    }))


def main():
    if len(sys.argv) == 4:
        worker(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
        return
    matriz = [(512, 32), (512, 8), (256, 32), (256, 8), (128, 8), (off := None, None)]
    saida = []
    for ml, b in matriz[:-1]:
        out = subprocess.run([sys.executable, __file__, str(ml), str(b), "3"],
                             capture_output=True, text=True, timeout=1800)
        if out.returncode != 0:
            print(f"{ml}/{b} FALHOU: {out.stderr[-500:]}")
            continue
        d = json.loads(out.stdout.strip().splitlines()[-1])
        saida.append(d)
        print(d, flush=True)
    path = os.path.expanduser("~/git/mms/lab-recall/eval/lab_rerank_rss_fresh.json")
    json.dump({"nota": "processo fresco por config, 3 repeticoes x 2 lotes",
               "configs": saida}, open(path, "w"), indent=2)
    print("artefato:", path)


if __name__ == "__main__":
    main()
