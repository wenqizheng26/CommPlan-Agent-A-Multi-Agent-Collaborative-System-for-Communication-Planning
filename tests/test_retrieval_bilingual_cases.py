"""W4-2 label integrity, index drift, metric denominators and output protection."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from eval_retrieval_bilingual import (DEFAULT_CASES,DOC_IDS,load_cases,metrics,
    run,summarize,validate_index,index_fingerprint)
from planning.retrieval import DefaultRetrievalService


class BilingualCaseTests(unittest.TestCase):
    def test_frozen_cases_have_complete_pairs_labels_and_allocation(self):
        meta,cases=load_cases()
        self.assertEqual((len(cases),meta['index']['total_chunks'],meta['index']['filtered_chunks']),(48,321,305))
        self.assertEqual(len({c['query'] for c in cases}),48)
        self.assertEqual(sum(c['colloquial'] for c in cases),8)

    def test_labels_match_the_current_hash_verified_index(self):
        meta,cases=load_cases()
        service=DefaultRetrievalService(ROOT,[])
        try: current=validate_index(meta,cases,service)
        except FileNotFoundError as exc: self.skipTest(str(exc))
        self.assertEqual(current,meta['index'])

    def test_changed_chunking_requires_reannotation(self):
        # A one-character chunk edit changes the fingerprint even without count/id changes.
        chunks=[dict(id='doc:itu-p525-5:p4-1',doc_id='itu-p525-5',description='a',sources=[dict(sha256='a'*64)])]
        meta=dict(documents=[dict(doc_id='itu-p525-5',sha256='a'*64)],index=dict(
            total_chunks=1,filtered_chunks=1,chunk_index_sha256=index_fingerprint(chunks)))
        service=SimpleNamespace(documents=SimpleNamespace(chunks=copy.deepcopy(chunks),
            records=meta['documents'],status=[dict(doc_id='itu-p525-5',status='ready')]))
        service.documents.chunks[0]['description']='b'
        with self.assertRaisesRegex(ValueError,'重新标注'): validate_index(meta,[],service)

    def test_missing_itu_source_is_distinct_from_changed_source(self):
        meta=dict(documents=[dict(doc_id='itu-p525-5',sha256='a'*64)])
        store=SimpleNamespace(chunks=[],records=meta['documents'],status=[dict(doc_id='itu-p525-5',status='not_installed')])
        with self.assertRaises(FileNotFoundError): validate_index(meta,[],SimpleNamespace(documents=store))
        store.status[0]['status']='changed'
        with self.assertRaises(ValueError): validate_index(meta,[],SimpleNamespace(documents=store))

    def test_invalid_pair_or_page_is_rejected(self):
        rows=[json.loads(l) for l in DEFAULT_CASES.read_text(encoding='utf-8').splitlines()]
        for mutation in ('language','page'):
            changed=copy.deepcopy(rows)
            if mutation=='language': changed[2]['language']='zh'
            else: changed[1]['gold'][0]['page']=999
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'cases.jsonl'
                path.write_text('\n'.join(json.dumps(r) for r in changed),encoding='utf-8')
                with self.assertRaises(ValueError): load_cases(path)

    def test_metrics_use_rank_relevant_set_and_doc_page(self):
        gold=[dict(chunk_id=f'doc:itu-p525-5:p4-{i}',page=4,reason='label') for i in (1,2,3)]
        hits=[dict(id='doc:itu-p530-19:p4-1',doc_id='itu-p530-19',page=4),
              dict(id='doc:itu-p525-5:p4-8',doc_id='itu-p525-5',page=4),
              dict(id='doc:itu-p525-5:p4-2',doc_id='itu-p525-5',page=4)]
        self.assertEqual(metrics(gold,hits),dict(hit_at_1=0,hit_at_5=1,mrr_at_10=1/3,recall_at_5=1/3,page_hit_at_5=1))
        self.assertEqual(metrics(gold,hits[:1])['page_hit_at_5'],0)
        self.assertEqual(metrics(gold,[])['mrr_at_10'],0)

    def test_run_keeps_only_ids_pages_scores_and_records_degradation(self):
        _,cases=load_cases(); calls=[]
        class Fake:
            def search(self,query,**kwargs):
                calls.append(kwargs)
                return SimpleNamespace(hits=[dict(id='doc:itu-p525-5:p4-1',rank=1,
                    source=dict(doc_id='itu-p525-5'),scores=dict(lexical=0.5,dense=None),
                    excerpt='DO NOT EXPORT ITU TEXT',title='DO NOT EXPORT ITU TITLE')],
                    mode_used='lexical',degraded=kwargs['mode']!='lexical',embedding_model_id=None,
                    reranker_id=None,latency_ms=dict(total=3),diagnostics=[dict(code='EMBEDDING_NOT_READY')])
        rows=run(Fake(),cases[:2])
        self.assertEqual(len(rows),6)
        self.assertNotIn('DO NOT EXPORT',json.dumps(rows))
        self.assertTrue(all(c['filters']=={'doc_ids':DOC_IDS} and c['top_k']==10 for c in calls))
        summaries=summarize(rows)
        self.assertEqual(len(summaries),6)
        self.assertEqual([s['degraded_count'] for s in summaries],[0,0,1,1,1,1])

    def test_existing_output_is_preserved_before_model_or_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'first.json'; path.write_bytes(b'first baseline')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/eval_retrieval_bilingual.py'),'--output',str(path)],
                                  capture_output=True,text=True,encoding='utf-8')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('refusing to overwrite',result.stderr)
            self.assertEqual(path.read_bytes(),b'first baseline')


if __name__=='__main__': unittest.main()
