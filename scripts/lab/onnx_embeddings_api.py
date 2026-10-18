"""API de embeddings OpenAI-compatible servida pelo ONNX local do mms.

Existe por um motivo específico: o migrador oficial do produto
(`scripts/maintenance/migrate_embeddings.py`) fala apenas HTTP OpenAI-compatible,
enquanto o serviço embebe com ONNX local. Em vez de reescrever o migrador — e com
ele perder a validação que já tem (backup, recriação da vec0, rebuild de FTS,
VACUUM, verificação de integridade) — subimos esta ponte e apontamos o migrador
para ela.

Uso:
    python onnx_embeddings_api.py --model paraphrase-multilingual-MiniLM-L12-v2 --port 8799
    curl -s localhost:8799/v1/embeddings -H 'Content-Type: application/json' \
        -d '{"input":["teste"],"model":"x"}' | head -c 200
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np


def build_handler(model_name: str):
    from mcp_memory_service.embeddings.onnx_embeddings import get_onnx_embedding_model

    model = get_onnx_embedding_model(model_name)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # silencia o log de acesso
            return

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") in ("/health", "/v1/models"):
                self._send(200, {"status": "ok", "model": model_name})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/v1/embeddings":
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(length) or b"{}")
                raw = req.get("input")
                texts = [raw] if isinstance(raw, str) else list(raw or [])
                if not texts:
                    self._send(400, {"error": "input vazio"})
                    return
                vecs = np.asarray(model.encode(texts), dtype=np.float32)
                data = [
                    {"object": "embedding", "index": i, "embedding": vecs[i].tolist()}
                    for i in range(len(texts))
                ]
                self._send(
                    200,
                    {
                        "object": "list",
                        "data": data,
                        "model": model_name,
                        "usage": {"prompt_tokens": 0, "total_tokens": 0},
                    },
                )
            except Exception as exc:  # devolve erro claro em vez de derrubar o servidor
                self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    handler = build_handler(args.model)
    srv = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"embeddings API em http://{args.host}:{args.port}/v1/embeddings · modelo {args.model}",
          flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
