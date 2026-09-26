"""Record C12's fixed queries without redistributing document text."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from formula_rag.catalog import load_catalog
from planning.providers.registry import Registry
from planning.retrieval import DefaultRetrievalService
from planning.retrieval.http_encoder import HTTPEncoder

QUERIES=['自由空间损耗公式','视距与等效地球半径','k 因子取值','海面反射与多径衰落',
         '衰落余量','A站坐标与天线高度','XX-100 发射功率','XX-200 接收灵敏度']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; retain first-run evidence')
    registry=Registry(ROOT);model=registry.models[registry.defaults['embedding']]
    cache=ROOT/'runtime/embedding-cache'
    service=DefaultRetrievalService(ROOT,load_catalog(ROOT),embedding_id=model['id'],
        embedding_path=model['weights'],encoder_factory=lambda _:HTTPEncoder(model,cache))
    start=time.perf_counter();status=service.warm(wait=True)
    result=dict(embedding=model['id'],revision=model['revision'],warm_status=status,
        warm_seconds=time.perf_counter()-start,documents=service.documents.describe(),results=[])
    for query in QUERIES:
        for mode in ('lexical','dense','hybrid'):
            row=service.search(query,top_k=3,top_n=3,mode=mode,filters={'source_type':'document_chunk'}).to_dict()
            for hit in row['hits']:
                hit.pop('excerpt',None)
            row['query']=query;result['results'].append(row)
            print(query,mode,row['mode_used'],round(row['latency_ms']['total']),flush=True)
    result['cache_bytes']=sum(p.stat().st_size for p in cache.glob('*.json'))
    result['passed']=status=='ready' and all(not row['degraded'] for row in result['results'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
