"""Busca profunda: recuperação vetorial + reranking ONNX, sob demanda.

Existe porque a medição mostrou a troca certa: o caminho interativo custa 155 ms e
entrega 0,575 de acerto por documento; reranquear 40 candidatos com cross-encoder
int8 custa ~1,3 s e sobe para ~0,70. Não é padrão — é opção, para quando a pergunta
merece profundidade.

Sem torch: onnxruntime + tokenizers, modelo int8 leve (bge-reranker-base, ~280 MB).

Uso:
    PYTHONPATH=src python scripts/deep_search.py "por que decidimos nao usar RAG" -n 5
    PYTHONPATH=src python scripts/deep_search.py "..." --store mir --candidates 60
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

REPO = "Xenova/bge-reranker-base"
ONNX = "onnx/model_int8.onnx"
MODELO_NOME = "bge-reranker-base-int8"


def mcp(port: int, name: str, arguments: dict) -> str:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    raw = urllib.request.urlopen(req, timeout=60).read().decode()
    for line in raw.splitlines():
        if line.startswith("data: "):
            d = json.loads(line[6:])
            if "result" in d:
                return d["result"]["content"][0]["text"]
    return ""


def parse_resultados(txt: str) -> list[dict]:
    """Converte o texto do memory_search em itens (conteúdo + metadados)."""
    itens, atual = [], None
    for bruta in txt.splitlines():
        linha = bruta.strip()
        if linha[:1].isdigit() and ". " in linha[:4]:
            if atual:
                itens.append(atual)
            atual = {"titulo": linha.split(". ", 1)[1][:120], "corpo": []}
        elif atual is not None:
            if linha.startswith("Hash:"):
                atual["hash"] = linha.split(":", 1)[1].strip()
            elif linha.strip():
                atual["corpo"].append(linha.strip())
    if atual:
        itens.append(atual)
    for i in itens:
        i["texto"] = i["titulo"] + "\n" + "\n".join(i["corpo"])
    return itens


class Ranker:
    def __init__(self, max_len: int = 128):
        t0 = time.time()
        self.tok = Tokenizer.from_file(hf_hub_download(REPO, "tokenizer.json"))
        self.tok.enable_truncation(max_length=max_len)
        self.tok.enable_padding(pad_id=1, pad_token="[PAD]")
        self.sess = ort.InferenceSession(
            hf_hub_download(REPO, ONNX), providers=["CPUExecutionProvider"]
        )
        self.nomes = {i.name for i in self.sess.get_inputs()}
        self.load_s = round(time.time() - t0, 2)

    def scores(self, pares: list[tuple[str, str]], batch: int = 32) -> list[float]:
        out: list[float] = []
        for i in range(0, len(pares), batch):
            lote = pares[i : i + batch]
            enc = self.tok.encode_batch([list(p) for p in lote])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.nomes:
                feeds["token_type_ids"] = np.zeros_like(ids)
            r = self.sess.run(None, feeds)[0]
            out.extend(np.asarray(r).reshape(len(lote), -1)[:, 0].tolist())
        return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("-n", "--limit", type=int, default=5)
    ap.add_argument("--candidates", type=int, default=40)
    ap.add_argument("--store", default="default")
    ap.add_argument("--port", type=int, default=3202)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dedupe", type=float, default=0.8,
                    help="colapsa resultados com Jaccard >= valor (0 desliga)")
    args = ap.parse_args()

    t0 = time.time()
    txt = mcp(args.port, "memory_search",
              {"query": args.query, "mode": "semantic",
               "limit": args.candidates, "store": args.store})
    t_busca = time.time() - t0
    itens = parse_resultados(txt)
    if not itens:
        print("nada encontrado", file=sys.stderr)
        return 1

    ranker = Ranker()
    t1 = time.time()
    sc = ranker.scores([(args.query, i["texto"]) for i in itens])
    t_rerank = time.time() - t1
    ordem = sorted(range(len(sc)), key=lambda j: -sc[j])

    if args.dedupe > 0:
        # Quase-duplicatas: o harvest grava a MESMA decisão em paráfrases
        # diferentes, e o cross-encoder as promove juntas. Dedup por conjunto de
        # palavras é suficiente para legibilidade e não custa embedding.
        def toks(t: str) -> set[str]:
            return {w for w in "".join(c if c.isalnum() else " " for c in t.lower()).split() if len(w) > 3}

        mantidos, assinaturas = [], []
        for j in ordem:
            corpo = " ".join(l for l in itens[j]["corpo"]
                             if not l.startswith(("Created:", "Hash:")))
            a = toks(itens[j]["titulo"] + " " + corpo[:400])
            if any(len(a & b) / max(len(a | b), 1) >= args.dedupe for b in assinaturas):
                continue
            mantidos.append(j)
            assinaturas.append(a)
        ordem = mantidos
    ordem = ordem[: args.limit]

    if args.json:
        print(json.dumps({
            "query": args.query,
            "ms_busca": round(t_busca * 1000),
            "ms_rerank": round(t_rerank * 1000),
            "ms_carga_modelo": round(ranker.load_s * 1000),
            "candidatos": len(itens),
            "resultados": [{"score": round(sc[j], 4), "titulo": itens[j]["titulo"], "hash": itens[j].get("hash")} for j in ordem],
        }, ensure_ascii=False, indent=1))
        return 0

    print(f"busca {t_busca*1000:.0f} ms · rerank {t_rerank*1000:.0f} ms "
          f"({len(itens)} candidatos, modelo {MODELO_NOME})")
    for pos, j in enumerate(ordem, 1):
        print(f"\n{pos}. [{sc[j]:.3f}] {itens[j]['titulo']}")
        print("   " + "\n   ".join(itens[j]["corpo"][:3])[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
