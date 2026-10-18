"""Fase 1 do reranking: extrai candidatos do índice (roda no venv do mms)."""
import argparse, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts', 'benchmarks'))
from recall_harness import load_cases, make_runner

ap = argparse.ArgumentParser()
ap.add_argument('--db', required=True)
ap.add_argument('--cases', default='eval/recall_cases_v3.json')
ap.add_argument('--model', default='paraphrase-multilingual-MiniLM-L12-v2')
ap.add_argument('--kmax', type=int, default=100)
ap.add_argument('--out', required=True)
a = ap.parse_args()

runner = make_runner(a.db, embedding_model=a.model)
out = []
for c in load_cases(a.cases):
    res = runner(c['pergunta'], 'semantic', a.kmax)
    out.append({'id': c['id'], 'pergunta': c['pergunta'],
                'gold': c.get('gold_hashes') or [],
                'hashes': [r.get('content_hash') for r in res],
                'contents': [(r.get('content') or '')[:1500] for r in res]})
json.dump(out, open(a.out, 'w'), ensure_ascii=False)
print(json.dumps({'casos': len(out), 'candidatos_por_caso': a.kmax, 'out': a.out}))
