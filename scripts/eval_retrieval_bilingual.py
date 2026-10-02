"""Frozen W4-2 bilingual document retrieval baseline; never change retrieval here."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from formula_rag.catalog import load_catalog
from planning.providers.registry import Registry
from planning.retrieval import DefaultRetrievalService, MODES
from planning.retrieval.http_encoder import HTTPEncoder
from planning.services.model_status import probe_model

DOC_IDS = ['itu-p525-5', 'itu-p530-19', 'itu-p453-14']
DEFAULT_CASES = ROOT / 'tests/eval/retrieval_bilingual.jsonl'


def page_of(chunk_id):
    match = re.fullmatch(r'doc:([^:]+):p(\d+)-\d+', chunk_id)
    if not match:
        raise ValueError('Expected a paged document chunk ID: ' + chunk_id)
    return int(match[2])


def index_fingerprint(chunks):
    rows = sorted((c['id'], c['sources'][0]['sha256'],
                   hashlib.sha256(c['description'].encode()).hexdigest()) for c in chunks)
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def load_cases(path=DEFAULT_CASES):
    rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows or rows[0].get('type') != 'metadata' or rows[0].get('schema_version') != 1:
        raise ValueError('Missing bilingual metadata header')
    meta, cases = rows[0], rows[1:]
    if len(cases) != 48 or {r['doc_id'] for r in meta['documents']} != set(DOC_IDS):
        raise ValueError('Expected three documents and 48 cases')
    for doc in meta['documents']:
        if not re.fullmatch('[a-f0-9]{64}', doc['sha256']):
            raise ValueError('Invalid source SHA-256')
    pairs, ids = defaultdict(dict), set()
    for case in cases:
        required = {'type','id','pair_id','language','doc_id','topic','query','colloquial','gold'}
        if (set(case) != required or case['type'] != 'case' or case['language'] not in ('zh','en')
                or case['doc_id'] not in DOC_IDS or case['id'] in ids
                or type(case['colloquial']) is not bool
                or not all(isinstance(case[k],str) and case[k].strip() for k in ('id','pair_id','query','topic'))
                or case['language'] in pairs[case['pair_id']]):
            raise ValueError('Invalid or duplicate bilingual case')
        ids.add(case['id'])
        if not isinstance(case['gold'],list) or not 1 <= len(case['gold']) <= 3:
            raise ValueError('Each case requires 1–3 relevant chunks')
        gold_ids = set()
        for gold in case['gold']:
            if (set(gold) != {'chunk_id','page','reason'} or type(gold['page']) is not int
                    or gold['page'] != page_of(gold['chunk_id'])
                    or not gold['chunk_id'].startswith('doc:'+case['doc_id']+':')
                    or gold['chunk_id'] in gold_ids or not isinstance(gold['reason'],str) or not gold['reason'].strip()):
                raise ValueError('Invalid gold chunk, page or relevance reason')
            gold_ids.add(gold['chunk_id'])
        pairs[case['pair_id']][case['language']] = case
    if len(pairs) != 24 or any(set(pair) != {'zh','en'} for pair in pairs.values()):
        raise ValueError('Expected 24 complete Chinese/English pairs')
    for pair in pairs.values():
        if any(pair['zh'][key] != pair['en'][key] for key in ('doc_id','topic','gold')):
            raise ValueError('Paired questions must have identical topics and labels')
    if Counter(p['zh']['doc_id'] for p in pairs.values()) != Counter({'itu-p525-5':4,'itu-p530-19':14,'itu-p453-14':6}):
        raise ValueError('Document allocation must be 4/14/6')
    if sum(c['colloquial'] for c in cases if c['language']=='zh') != 8 or any(c['colloquial'] for c in cases if c['language']=='en'):
        raise ValueError('Expected exactly eight colloquial Chinese questions')
    return meta, cases


def validate_index(meta, cases, service):
    chunks = service.documents.chunks
    records = {r['doc_id']:r for r in service.documents.records}
    ready = {r['doc_id']:r['status'] for r in service.documents.status}
    for doc in meta['documents']:
        if ready.get(doc['doc_id']) == 'not_installed':
            raise FileNotFoundError('ITU source unavailable: '+doc['doc_id'])
        if ready.get(doc['doc_id']) != 'ready':
            raise ValueError('ITU source changed or unreadable; re-annotate bilingual gold labels')
        if records[doc['doc_id']]['sha256'] != doc['sha256']:
            raise ValueError('ITU source changed; re-annotate bilingual gold labels')
    by_id = {c['id']:c for c in chunks}
    current = dict(total_chunks=len(chunks), filtered_chunks=sum(c['doc_id'] in DOC_IDS for c in chunks),
                   chunk_index_sha256=index_fingerprint(chunks))
    if current != meta['index']:
        raise ValueError('Document chunking changed; re-annotate bilingual gold labels (重新标注)')
    if any(g['chunk_id'] not in by_id for c in cases for g in c['gold']):
        raise ValueError('Gold chunk missing; re-annotate bilingual gold labels')
    return current


def metrics(gold, hits):
    relevant = {g['chunk_id'] for g in gold}
    pages = {(g['chunk_id'].split(':')[1], g['page']) for g in gold}
    ranks = [i for i,h in enumerate(hits[:10],1) if h['id'] in relevant]
    return dict(hit_at_1=float(bool(ranks and ranks[0]==1)),
                hit_at_5=float(bool(ranks and ranks[0]<=5)),
                mrr_at_10=1/ranks[0] if ranks else 0.0,
                recall_at_5=len(relevant & {h['id'] for h in hits[:5]})/len(relevant),
                page_hit_at_5=float(any((h['doc_id'],h['page']) in pages for h in hits[:5])))


def summarize(rows):
    groups = defaultdict(list)
    for row in rows: groups[(row['mode_requested'],row['language'])].append(row)
    summary = []
    for (mode,language),items in groups.items():
        latency = sorted(r['latency_ms']['total'] for r in items)
        summary.append(dict(mode=mode,language=language,count=len(items),
            **{key:sum(r['metrics'][key] for r in items)/len(items) for key in items[0]['metrics']},
            degraded_count=sum(r['degraded'] for r in items),
            latency_ms=dict(mean=sum(latency)/len(latency),p50=latency[math.ceil(len(latency)*0.5)-1],
                            p95=latency[math.ceil(len(latency)*0.95)-1])))
    return summary


def run(service, cases):
    rows=[]
    for mode in MODES:
        for i,case in enumerate(cases,1):
            result=service.search(case['query'],mode=mode,top_k=10,top_n=10,filters={'doc_ids':DOC_IDS})
            # Explicit allowlist: never serialize excerpts, titles or source passages.
            hits=[dict(id=h['id'],doc_id=h['source']['doc_id'],page=page_of(h['id']),
                       rank=h['rank'],scores=h['scores']) for h in result.hits]
            rows.append(dict(case_id=case['id'],pair_id=case['pair_id'],language=case['language'],
                mode_requested=mode,mode_used=result.mode_used,degraded=result.degraded,
                embedding_model_id=result.embedding_model_id,reranker_id=result.reranker_id,
                latency_ms=result.latency_ms,diagnostic_codes=[d['code'] for d in result.diagnostics],
                hits=hits,metrics=metrics(case['gold'],hits)))
            if i%12==0: print(f'{mode}: {i}/{len(cases)}',flush=True)
    return rows


def git_value(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True,encoding='utf-8').strip()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',type=Path,default=DEFAULT_CASES)
    args=parser.parse_args(argv)
    if args.output.exists(): parser.error('Output already exists; refusing to overwrite: '+str(args.output))
    meta,cases=load_cases(args.cases)
    registry=Registry(ROOT)
    model=registry.models[registry.defaults['embedding']]
    if model['id']!='qwen3-embedding-0.6b-q8': parser.error('Expected the registered Qwen3-Embedding 0.6B')
    service=DefaultRetrievalService(ROOT,load_catalog(ROOT),embedding_id=model['id'],
        remote_encoder=True,encoder_factory=lambda path:HTTPEncoder(model,ROOT/'runtime/embedding-cache'))
    index=validate_index(meta,cases,service)
    if probe_model(model['endpoint'],model['alias'])['status']!='ready':
        import start_commplan
        start_commplan.ensure_embedding(SimpleNamespace(asset_root=None))
    if probe_model(model['endpoint'],model['alias'])['status']!='ready':
        parser.error('Qwen3 embedding service is not ready; no formal baseline was run')
    print('Warming existing retrieval implementation...',flush=True)
    if service.warm(wait=True)!='ready': parser.error('Embedding warm-up failed: '+str(service.dense_error))
    started=datetime.now(timezone.utc).isoformat()
    rows=run(service,cases)
    result=dict(schema_version=1,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),
        code_commit=git_value('rev-parse','HEAD'),cases_commit=git_value('log','-1','--format=%H','--',str(args.cases.resolve())),
        cases_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        source_metadata=meta,index=index,embedding=dict(id=model['id'],alias=model['alias'],revision=model.get('revision'),
        endpoint=model['endpoint'],warm_ms=service.warm_ms),filters={'doc_ids':DOC_IDS},top_k=10,
        summary=summarize(rows),rows=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__': main()
