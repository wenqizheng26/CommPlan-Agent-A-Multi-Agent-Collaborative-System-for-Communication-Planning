import json
from pathlib import Path
import tempfile
import unittest
import time
import threading
from unittest.mock import patch
from planning.retrieval.http_encoder import HTTPEncoder
from launch import embedding_command, RUNTIME
from planning.providers.registry import Registry

ROOT=Path(__file__).resolve().parents[1]


class HTTPEmbeddingTests(unittest.TestCase):
    def test_service_has_wall_clock_budget_even_if_transport_drips(self):
        import numpy as np
        from planning.retrieval.service import DefaultRetrievalService
        from formula_rag.catalog import load_catalog
        release=threading.Event()
        class Slow:
            query_budget=True
            def encode(self,*args,**kwargs):
                release.wait(4)
                return np.array([[1.,0.,0.]])
        service=DefaultRetrievalService(ROOT,load_catalog(ROOT))
        start=time.monotonic()
        try:
            with self.assertRaises(TimeoutError):service._query(Slow(),'question',.05)
            self.assertLess(time.monotonic()-start,.3)
            with self.assertRaisesRegex(TimeoutError,'BUSY'):service._query(Slow(),'question',.05)
        finally:release.set()

    def test_external_http_weights_and_retry_after_transient_failure(self):
        import numpy as np
        from planning.retrieval.service import DefaultRetrievalService
        from formula_rag.catalog import load_catalog
        class Encoder:
            calls=0
            def encode(self,texts,**kwargs):
                self.calls+=1
                if self.calls==1:raise ConnectionRefusedError()
                return np.ones((len(texts),3))
        encoder=Encoder()
        service=DefaultRetrievalService(ROOT,load_catalog(ROOT),embedding_id='remote',embedding_path='absent.gguf',
            encoder_factory=lambda p:encoder,remote_encoder=True)
        self.assertEqual(service.warm(wait=True),'failed')
        self.assertEqual(service.warm(wait=True),'failed');self.assertEqual(encoder.calls,1)
        service.retry_after=0
        self.assertEqual(service.warm(wait=True),'ready');self.assertIsNone(service.dense_error)

    def test_query_instruction_cache_and_revision(self):
        model=dict(id='fake',alias='fake',endpoint='http://127.0.0.1:18084',dimension=3,revision='one')
        payload=dict(model='fake',data=[dict(index=0,embedding=[1,2,3])])
        with tempfile.TemporaryDirectory() as temporary, patch('planning.retrieval.http_encoder.build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=json.dumps(payload).encode()
            encoder=HTTPEncoder(model,temporary)
            first=encoder.encode(['passage'])
            self.assertEqual(opener.return_value.open.call_count,1)
            self.assertTrue((first==encoder.encode(['passage'])).all())
            self.assertEqual(opener.return_value.open.call_count,1)
            encoder.corpus_hash='changed document SHA'
            encoder.encode(['passage'])
            self.assertEqual(opener.return_value.open.call_count,2)
            encoder.encode(['question'],query=True)
            request=opener.return_value.open.call_args.args[0]
            self.assertIn('Instruct:',json.loads(request.data)['input'][0])
            model['revision']='two'
            encoder.encode(['passage'])
            self.assertEqual(opener.return_value.open.call_count,4)

    def test_remote_endpoint_bad_dimension_and_nan_are_rejected(self):
        model=dict(id='fake',alias='fake',endpoint='https://example.com',dimension=3)
        with self.assertRaises(ValueError):HTTPEncoder(model)
        model['endpoint']='http://127.0.0.1:18084'
        encoder=HTTPEncoder(model)
        for row in ([1,2],[float('nan'),1,2],[0,0,0]):
            with self.assertRaises(ValueError):encoder._validate(row)

    def test_cpu_launch_is_separate_and_has_noncausal_batch_capacity(self):
        registry=Registry(ROOT)
        model=registry.models[registry.defaults['embedding']]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for p in (root/model['weights'],root/'models/signal-formula-qwen3'/RUNTIME):
                p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
            command=embedding_command(root,registry_root=ROOT)
        self.assertIn('--embedding',command)
        for option in ('-c','-b','-ub'):
            self.assertGreaterEqual(int(command[command.index(option)+1]),2048)
        self.assertEqual(command[command.index('-ngl')+1],'0')
        # No GPU at all: batch offload would take memory the chat model needs.
        self.assertEqual(command[command.index('--device')+1],'none')
        self.assertEqual(command[command.index('--pooling')+1],'last')
        self.assertEqual(command[command.index('--port')+1],'18084')


if __name__=='__main__':unittest.main()
