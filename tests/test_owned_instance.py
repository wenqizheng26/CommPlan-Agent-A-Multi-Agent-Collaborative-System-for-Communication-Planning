import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import owned_instance as owned  # noqa: E402

FAKE_MODEL = '''import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
alias, port = sys.argv[1], int(sys.argv[2])
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_GET(self):
        body = {'/health': {'status': 'ok'}, '/v1/models': {'data': [{'id': alias}]}}.get(self.path)
        data = json.dumps(body).encode()
        self.send_response(200 if body else 404)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
HTTPServer(('127.0.0.1', port), Handler).serve_forever()
'''
# The interpreter itself, not a venv launcher: like llama-server, it listens in the started process.
BASE_PYTHON = getattr(sys, '_base_executable', sys.executable)


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def post(url, headers=None, body=b''):
    request = Request(url, data=body, headers=headers or {}, method='POST')
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        with exc:
            return exc.code, json.load(exc)


@unittest.skipUnless(os.name == 'nt', 'Windows process handles')
class OwnedInstanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='owned-'))
        self.addCleanup(self.cleanup)
        self.fake = self.tmp / 'fake_model.py'
        self.fake.write_text(FAKE_MODEL, encoding='utf-8')
        self.record = self.tmp / 'instance.json'
        self.extra = []

    def cleanup(self):
        try:
            if self.record.exists() and owned.load(self.record)['state'] == 'running':
                owned.stop(self.record, drain_s=5)
        except Exception:
            pass
        for process in self.extra:
            if process.poll() is None:
                process.kill()
                process.wait(10)
        for _ in range(20):
            try:
                import shutil
                shutil.rmtree(self.tmp)
                return
            except OSError:
                time.sleep(0.5)

    def model(self, role, alias, port):
        return {'role': role, 'alias': alias, 'port': port, 'cwd': str(self.tmp),
                'command': [BASE_PYTHON, '-B', str(self.fake), alias, str(port)]}

    def foreign(self, alias, port):
        process = subprocess.Popen([BASE_PYTHON, '-B', str(self.fake), alias, str(port)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.extra.append(process)
        deadline = time.monotonic() + 20
        while not owned.model_answers(port, alias):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.2)
        return process

    def plan(self, workbench=None, models=True):
        from planning.build_info import build_fingerprint
        port = free_port()
        services = [self.model('chat', 'fake-chat', free_port()), self.model('embedding', 'fake-embed', free_port())] \
            if models else []
        services.append(workbench or {
            'role': 'workbench', 'alias': None, 'port': port, 'cwd': str(ROOT),
            'command': [sys.executable, '-B', '-X', 'utf8', '-m', 'planning.web_server', '--root', str(ROOT),
                        '--db', str(self.tmp / 'web.sqlite'), '--port', str(port)]})
        return {'app_root': str(ROOT), 'python': sys.executable, 'db': str(self.tmp / 'web.sqlite'),
                'asset_root': str(self.tmp), 'build': build_fingerprint(ROOT), 'services': services}

    def test_start_status_stop_touches_only_its_own_processes(self):
        plan = self.plan()
        chat = plan['services'][0]['port']
        record = owned.start(self.record, plan)
        self.assertEqual(record['state'], 'running')
        saved = owned.load(self.record)
        self.assertEqual(saved['instance'], owned.instance_id(saved['secret']))
        self.assertEqual(owned.status(saved)['services'],
                         {'chat': 'running', 'embedding': 'running', 'workbench': 'running'})
        for row in saved['services']:
            # Listener cross-check: the started process or its child holds the port.
            self.assertEqual(owned.listeners(row['port']), {row['server']['pid']})
        base = saved['workbench']
        with urlopen(base + '/api/session', timeout=10) as response:
            session = json.load(response)
        self.assertEqual(session['instance_id'], saved['instance'])
        self.assertNotIn(saved['secret'], json.dumps(session))
        token = {'X-Planning-Token': session['token'], 'Content-Type': 'application/json'}
        code, body = post(base + '/api/model-switch', token, json.dumps({'model_id': 'qwen3-4b-q4'}).encode())
        self.assertEqual((code, body['error']['code']), (409, 'MODEL_SWITCH_DISABLED'))
        # The secret is never on a command line.
        for row in saved['services']:
            self.assertNotIn(saved['secret'], row['process']['command_line'])
            self.assertNotIn(saved['secret'], row['server']['command_line'])

        # A fresh process reads the record back (CLI status), then stops by it.
        cli = [sys.executable, '-B', str(ROOT / 'scripts/owned_instance.py')]
        result = subprocess.run(cli + ['status', '--record', str(self.record)], capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['state'], 'running')
        result = subprocess.run(cli + ['stop', '--record', str(self.record)], capture_output=True, text=True,
                                timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['services'],
                         {'workbench': 'stopped', 'chat': 'stopped', 'embedding': 'stopped'})
        saved = owned.load(self.record)
        self.assertEqual(saved['state'], 'stopped')
        self.assertEqual(owned.status(saved)['state'], 'stopped')
        for row in saved['services']:
            self.assertEqual(owned.open_saved(row['process'])[0], 'exited')
            self.assertFalse(owned.port_open(row['port']))
        # The same port is free again for anyone else; a stopped record stays as evidence.
        self.foreign('fake-chat', chat)
        result = subprocess.run(cli + ['status', '--record', str(self.record)], capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)['services']['chat'], 'exited')

    def test_busy_port_or_existing_record_starts_nothing_and_leaves_the_other_service(self):
        plan = self.plan()
        chat = plan['services'][0]
        other = self.foreign(chat['alias'], chat['port'])
        with self.assertRaisesRegex(owned.Refused, 'ports in use'):
            owned.start(self.record, plan)
        self.assertFalse(self.record.exists())
        self.record.write_text('{"keep": true}', encoding='utf-8')
        with self.assertRaisesRegex(owned.Refused, 'record already exists'):
            owned.start(self.record, self.plan())
        self.assertEqual(self.record.read_text(encoding='utf-8'), '{"keep": true}')
        self.assertIsNone(other.poll())
        self.assertTrue(owned.model_answers(chat['port'], chat['alias']))

    def test_record_that_no_longer_matches_is_foreign_and_never_stopped(self):
        plan = self.plan(models=False)
        plan['services'][:0] = [self.model('chat', 'fake-chat', free_port())]
        owned.start(self.record, plan)
        good = owned.load(self.record)
        chat = good['services'][0]
        # The same PID with another creation time is what PID reuse looks like.
        changed = json.loads(json.dumps(good))
        changed['services'][0]['process']['created'] += 1
        changed['services'][0]['server']['created'] += 1
        self.record.write_text(json.dumps(changed), encoding='utf-8')
        self.assertEqual(owned.status(changed)['services']['chat'], 'foreign')
        result = owned.stop(self.record, drain_s=5)
        self.assertEqual(result['stop']['services']['chat'], 'foreign')
        self.assertEqual(result['state'], 'stop-incomplete')
        self.assertTrue(owned.model_answers(chat['port'], 'fake-chat'))
        with owned.Process(chat['process']['pid']) as process:
            self.assertTrue(process.alive())
            process.terminate()
            self.assertTrue(process.wait(10))

    def test_listener_that_is_not_ours_is_refused(self):
        # The "started" process is an idle sibling; the listener is not its child.
        idle = subprocess.Popen([BASE_PYTHON, '-c', 'import time; time.sleep(60)'])
        self.extra.append(idle)
        port = free_port()
        other = self.foreign('fake', port)
        with owned.Process(idle.pid) as started:
            with self.assertRaisesRegex(owned.Refused, 'not started by this instance'):
                owned.server_of(started, port)
        self.assertIsNone(other.poll())

    def test_failed_start_stops_only_what_it_started(self):
        port = free_port()
        broken = {'role': 'workbench', 'alias': None, 'port': port, 'cwd': str(self.tmp),
                  'command': [BASE_PYTHON, '-B', '-c', 'import sys; sys.exit(3)']}
        plan = self.plan(broken)
        bystander = self.foreign('bystander', free_port())
        with self.assertRaisesRegex(owned.Refused, 'workbench exited early with 3'):
            owned.start(self.record, plan)
        saved = owned.load(self.record)
        self.assertEqual(saved['state'], 'failed')
        for row in saved['services'][:2]:
            self.assertEqual(owned.open_saved(row['process'])[0], 'exited')
        self.assertIsNone(bystander.poll())

    def test_cli_workbench_only_round_trip(self):
        port = free_port()
        cli = [sys.executable, '-B', str(ROOT / 'scripts/owned_instance.py')]
        result = subprocess.run(cli + ['start', '--app-root', str(ROOT), '--python', sys.executable,
                                       '--db', str(self.tmp / 'cli.sqlite'), '--record', str(self.record),
                                       '--port', str(port), '--without-model'],
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['workbench'], f'http://127.0.0.1:{port}')
        result = subprocess.run(cli + ['start', '--app-root', str(ROOT), '--python', sys.executable,
                                       '--db', str(self.tmp / 'cli.sqlite'), '--record', str(self.record),
                                       '--port', str(port), '--without-model'],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn('record already exists', result.stderr)
        result = subprocess.run(cli + ['stop', '--record', str(self.record)], capture_output=True, text=True,
                                timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(owned.port_open(port))


class InstanceEndpointTests(unittest.TestCase):
    """The workbench side: secret, token, no body, and waiting for running commands."""

    def setUp(self):
        from test_planning_loop import ROOT as APP_ROOT
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.web = importlib.import_module('planning.web_server')
        self.secret = 'instance-secret-for-test'
        self.server = self.web.create_server(APP_ROOT, Path(self.tmp.name) / 'web.sqlite', port=0,
                                             instance_secret=self.secret)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        with urlopen(self.base + '/api/session', timeout=15) as response:
            self.session = json.load(response)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def headers(self, **extra):
        return dict({'X-Planning-Token': self.session['token'], 'X-Instance-Secret': self.secret,
                     'Content-Type': 'application/json'}, **extra)

    def test_close_needs_token_secret_and_no_body(self):
        url = self.base + '/api/instance/shutdown'
        self.assertEqual(self.session['instance_id'], self.web.instance_id(self.secret))
        self.assertEqual(post(url, self.headers(**{'X-Instance-Secret': 'wrong'}))[0], 403)
        self.assertEqual(post(url, {'X-Instance-Secret': self.secret})[0], 403)
        self.assertEqual(post(url, self.headers(), b'{}')[0], 400)
        self.assertTrue(self.thread.is_alive())
        self.assertEqual(post(url, self.headers()), (200, {'stopping': True}))
        self.thread.join(timeout=10)
        self.assertFalse(self.thread.is_alive())

    def test_close_waits_for_a_running_command_and_then_refuses_new_ones(self):
        from test_planning_loop import command
        from planning.workflow.task_service import TaskService
        entered, release = threading.Event(), threading.Event()
        original = TaskService.apply

        def slow(service, payload):
            entered.set()
            release.wait(20)
            return original(service, payload)

        results = {}
        with mock.patch.object(TaskService, 'apply', slow), mock.patch.object(self.web, 'DRAIN_S', 0.5):
            worker = threading.Thread(target=lambda: results.update(
                create=post(self.base + '/api/commands', self.headers(), json.dumps(command()).encode())))
            worker.start()
            self.assertTrue(entered.wait(10))
            code, body = post(self.base + '/api/instance/shutdown', self.headers())
            self.assertEqual((code, body['error']['code']), (409, 'INSTANCE_BUSY'))
            release.set()
            worker.join(30)
        self.assertEqual(results['create'][0], 200)
        self.assertEqual(results['create'][1]['state']['status'], 'AWAITING_CONFIRMATION')
        stopping = threading.Event()
        with mock.patch.object(self.server, 'shutdown', side_effect=stopping.set):
            self.assertEqual(post(self.base + '/api/instance/shutdown', self.headers())[0], 200)
            self.assertTrue(stopping.wait(5))
            code, body = post(self.base + '/api/commands', self.headers(), json.dumps(command()).encode())
            self.assertEqual((code, body['error']['code']), (409, 'INSTANCE_STOPPING'))
            # Cancelling is still admitted: it is how a long command ends while a close waits.
            cancel = {'task_id': results['create'][1]['state']['task_id'], 'event_id': '00000000-0000-4000-8000-000000000001'}
            code, body = post(self.base + '/api/cancel-operation', self.headers(), json.dumps(cancel).encode())
            self.assertNotEqual(body.get('error', {}).get('code'), 'INSTANCE_STOPPING')

    def test_plain_workbench_has_no_close_endpoint(self):
        from test_planning_loop import ROOT as APP_ROOT
        server = self.web.create_server(APP_ROOT, Path(self.tmp.name) / 'plain.sqlite', port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base + '/api/session', timeout=15) as response:
                session = json.load(response)
            self.assertNotIn('instance_id', session)
            self.assertIsInstance(session['instance'], dict)
            code, _ = post(base + '/api/instance/shutdown', {'X-Planning-Token': session['token'],
                                                             'X-Instance-Secret': ''})
            self.assertEqual(code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
