"""Reranker leve, só ONNX — sem torch.

Decisão de projeto já tomada: nada de torch. Modelo leve, int8, onnxruntime puro
(que já existe no venv do mms, junto com `tokenizers`).

Compara candidatos sobre o mesmo dump de candidatos (top-30 do índice), medindo as
duas coisas que decidem: ganho de recall@10 e latência por consulta.

Uso:
    PYTHONPATH=src ~/git/mcp-memory-service/.venv/bin/python eval/onnx_rerank.py \
        --dump /tmp/cands30.json --limit 40 --out eval/lab_onnx_rerank.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

CANDIDATOS = [
    ("Xenova/ms-marco-MiniLM-L-6-v2", "onnx/model_int8.onnx", 256),
    ("Xenova/bge-reranker-base", "onnx/model_int8.onnx", 256),
    ("onnx-community/bge-reranker-v2-m3-ONNX", "onnx/model_int8.onnx", 256),
    ("onnx-community/bge-reranker-v2-m3-ONNX", "onnx/model_q4.onnx", 256),
]


def carregar(repo: str, onnx_file: str, max_len: int):
    tok = Tokenizer.from_file(hf_hub_download(repo, "tokenizer.json"))
    tok.enable_truncation(max_length=max_len)
    tok.enable_padding(pad_id=1, pad_token="[PAD]")
    path = hf_hub_download(repo, onnx_file)
    sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    nomes = {i.name for i in sess.get_inputs()}
    return tok, sess, nomes


def pontuar(tok, sess, nomes, pares, batch=32) -> np.ndarray:
    scores = []
    for i in range(0, len(pares), batch):
        lote = pares[i : i + batch]
        enc = tok.encode_batch([list(p) for p in lote])
        feeds = {}
        for cand in ("input_ids", "attention_mask", "token_type_ids"):
            if cand in nomes:
                feeds[cand] = np.array([e.ids for e in enc], dtype=np.int64) if cand == "input_ids" \
                    else np.array([e.attention_mask for e in enc], dtype=np.int64) if cand == "attention_mask" \
                    else np.zeros_like(np.array([e.ids for e in enc], dtype=np.int64))
        saida = sess.run(None, feeds)[0]
        scores.extend(np.asarray(saida).reshape(len(lote), -1)[:, 0].tolist())
    return np.asarray(scores)


def rec(pos, k):
    return round(sum(1 for p in pos if p and p <= k) / len(pos), 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--limit", type=int, default=40, help="nº de casos para medir (0 = todos)")
    ap.add_argument("--max-len", type=int, default=0, help="sobrescreve o comprimento máximo")
    ap.add_argument("--only", default="", help="filtra candidatos por substring do repo")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = json.load(open(args.dump))
    if args.limit:
        rows = rows[: args.limit]

    pos_base = [
        next((j + 1 for j, h in enumerate(r["hashes"]) if h in set(r["gold"])), None)
        for r in rows
    ]
    base = {f"documento@{k}": rec(pos_base, k) for k in (5, 10, 30)}

    resultado = {"casos": len(rows), "base": base, "modelos": {}}
    candidatos = [c for c in CANDIDATOS if (not args.only or args.only in c[0])]
    for repo, onnx_file, max_len in candidatos:
        if args.max_len:
            max_len = args.max_len
        try:
            tok, sess, nomes = carregar(repo, onnx_file, max_len)
        except Exception as exc:
            resultado["modelos"][f"{repo}:{onnx_file}"] = {"erro": f"{type(exc).__name__}: {exc}"[:160]}
            print(f"{repo} {onnx_file}: ERRO {exc}", flush=True)
            continue
        pos, lat = [], []
        for r in rows:
            pares = [(r["pergunta"], c) for c in r["contents"]]
            t0 = time.time()
            sc = pontuar(tok, sess, nomes, pares)
            lat.append((time.time() - t0) * 1000)
            order = sorted(range(len(sc)), key=lambda j: -float(sc[j]))
            pos.append(next((j + 1 for j, idx in enumerate(order) if r["hashes"][idx] in set(r["gold"])), None))
        chave = f"{repo}:{onnx_file.split('.')[-2]}"
        resultado["modelos"][chave] = {
            f"documento@{k}": rec(pos, k) for k in (5, 10, 30)
        } | {
            "ganho_top10": round(rec(pos, 10) - base["documento@10"], 4),
            "latencia_p50_ms": round(statistics.median(lat)),
            "ms_por_par": round(statistics.median(lat) / max(len(rows[0]["contents"]), 1), 1),
        }
        print(json.dumps({chave: resultado["modelos"][chave]}, ensure_ascii=False), flush=True)

    if args.out:
        json.dump(resultado, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(resultado, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
