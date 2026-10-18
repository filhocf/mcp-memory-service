"""Fase 2: reordena candidatos com cross-encoder (roda no venv do reranker)."""
import argparse, json, statistics, time
from sentence_transformers import CrossEncoder

ap = argparse.ArgumentParser()
ap.add_argument('--dump', required=True)
ap.add_argument('--ranker', default='BAAI/bge-reranker-v2-m3')
ap.add_argument('--out', required=True)
a = ap.parse_args()

def rec(pos, k):
    return round(sum(1 for p in pos if p and p <= k) / len(pos), 4)

rows = json.load(open(a.dump))
ranker = CrossEncoder(a.ranker, max_length=256, device='cpu')
before, after, lat = [], [], []
t0 = time.time()
for i, r in enumerate(rows, 1):
    gold = set(r['gold'])
    before.append(next((j+1 for j,h in enumerate(r['hashes']) if h in gold), None))
    pairs = [(r['pergunta'], c) for c in r['contents']]
    ts = time.time()
    sc = ranker.predict(pairs, batch_size=32, show_progress_bar=False)
    lat.append((time.time()-ts)*1000)
    order = sorted(range(len(sc)), key=lambda j: -float(sc[j]))
    after.append(next((j+1 for j,idx in enumerate(order) if r['hashes'][idx] in gold), None))
    if i % 20 == 0: print(f'  {i}/{len(rows)} {time.time()-t0:.0f}s', flush=True)

rep = {'meta': {'dump': a.dump, 'ranker': a.ranker, 'device': 'cpu'},
       'antes': {f'documento@{k}': rec(before,k) for k in (10,30,100)},
       'depois': {f'documento@{k}': rec(after,k) for k in (10,30,100)},
       'mudancas': {'subiu_para_top10': sum(1 for x,y in zip(before,after) if (x is None or x>10) and y and y<=10),
                    'saiu_do_top10': sum(1 for x,y in zip(before,after) if x and x<=10 and (y is None or y>10))},
       'custo': {'segundos': round(time.time()-t0,1), 'ms_por_consulta_p50': round(statistics.median(lat))}}
json.dump(rep, open(a.out,'w'), ensure_ascii=False, indent=1)
print(json.dumps(rep, ensure_ascii=False, indent=1))
