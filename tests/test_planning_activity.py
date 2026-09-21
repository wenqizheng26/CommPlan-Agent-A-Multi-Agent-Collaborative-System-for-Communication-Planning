import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_planning_loop import ROOT, command
from planning.workflow.task_service import TaskService
from planning.agents.requirements import RequirementsAgent


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = TaskService(ROOT, Path(self.tmp.name)/'tasks.sqlite')

    def test_started_visible_before_business_commit(self):
        entered, release = threading.Event(), threading.Event()
        original = RequirementsAgent.run
        def slow(agent, *args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('test release timed out')
            return original(agent, *args, **kwargs)
        c = command()
        with patch.object(RequirementsAgent, 'run', slow), ThreadPoolExecutor() as pool:
            future = pool.submit(self.service.apply, c)
            try:
                self.assertTrue(entered.wait(10))
                events = self.service.activity.events(c['task_id'])
                self.assertTrue(any(e['node']=='requirements' and e['phase']=='started' for e in events))
                with self.assertRaisesRegex(ValueError, 'TASK_NOT_FOUND'):
                    self.service.get(c['task_id'])
            finally:
                release.set()
            self.assertEqual(future.result()['state']['status'], 'AWAITING_CONFIRMATION')
        events = self.service.activity.events(c['task_id'])
        self.assertEqual(events[-1]['phase'], 'committed')
        self.assertTrue(any(e['node']=='confirmation' and e['phase']=='waiting' for e in events))

    def test_rollback_replay_and_revision_are_explicit(self):
        c = command()
        draft = self.service.apply(c)['state']
        self.service.apply(c)
        self.assertEqual(self.service.activity.events(c['task_id'])[-1]['phase'], 'replayed')
        with patch.object(self.service.store, 'save', side_effect=RuntimeError('disk')):
            with self.assertRaises(RuntimeError):
                self.service.apply(command('confirm', draft))
        events = self.service.activity.events(c['task_id'])
        self.assertEqual(events[-1]['phase'], 'rejected')
        self.assertEqual(self.service.get(c['task_id'])['status'], 'AWAITING_CONFIRMATION')
        edited = self.service.apply(command('edit', draft))['state']
        self.assertEqual(self.service.activity.events(c['task_id'])[-1]['revision'], edited['revision'])

    def test_restart_marks_only_unfinished_runs_interrupted(self):
        c = command()
        self.service.activity.start(c)
        self.service.activity.interrupt_open()
        events = self.service.activity.events(c['task_id'])
        self.assertEqual(events[-1]['phase'], 'interrupted')
        self.service.activity.interrupt_open()
        self.assertEqual(self.service.activity.events(c['task_id']), events)

    def test_optional_observation_failure_does_not_rollback_business(self):
        with patch.object(self.service.activity, 'append', side_effect=OSError('diagnostic disk')):
            state = self.service.apply(command())['state']
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')
