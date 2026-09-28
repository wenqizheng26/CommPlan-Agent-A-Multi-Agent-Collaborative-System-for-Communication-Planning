"""A follow-up that swaps the radio or one site makes a new revision to confirm (M1 week 4)."""
import copy
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from planning.agents.extraction import extract
from planning.knowledge.drafts import DraftStore
from planning.workflow.task_service import TaskService
from test_knowledge_drafts import TABLE, model
from test_requirement_facts import ask, labeller

ROOT = Path(__file__).resolve().parents[1]
RADIOS = ('XX-300', 'XX-200', 'XX-100')


def understand(text, candidates):
    """The stub model reads whichever second site and radio the current text names."""
    end = next((name for name in ('C', 'D', 'B') if f'{name} 站' in text or f'{name}站' in text), 'B')
    return labeller(text, end, next((r for r in RADIOS if r in text), 'XX-100'))(text, candidates)


class FollowupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'app'
        for folder in ('knowledge/documents', 'knowledge/facts', 'config'):
            shutil.copytree(ROOT / folder, self.root / folder)
        for name in ('knowledge/formulas.json', 'runtime_config.json'):
            shutil.copy(ROOT / name, self.root / name)
        self.service = TaskService(self.root, Path(temp.name) / 'followup.sqlite')
        self.followup = None  # what the stub model answers for the follow-up role

    def role(self, selector, role, prompt, view, schema):
        if role == 'followup' and self.followup is not None:
            answer = self.followup(view) if callable(self.followup) else self.followup
            return dict(output=copy.deepcopy(answer), raw_output='')
        raise OSError('no local model in tests')  # other roles fall back to the rules

    def apply(self, action, state=None, **extra):
        c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
                 expected_revision=state['revision'] if state else 0,
                 expected_state_version=state['state_version'] if state else 0, **extra)
        with patch('planning.workflow.task_service.LocalSelector', return_value=understand), \
                patch('planning.agents.role_model.LocalRoleSelector.__call__', autospec=True, side_effect=self.role):
            return self.service.apply(c)['state']

    def create(self, text=None):
        state = self.apply('create', input=dict(raw_text=text or ask(), manual_parameters={}, condition=None, target=None),
                           mode='llm')
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
        return state

    def ask_again(self, state, message):
        return self.apply('supplement', state, message=message, mode='llm')

    def swap(self, device='', replaced='', new=''):
        return dict(action='apply', new_device=device, replaced_site=replaced, new_site=new)

    def test_swapping_the_radio_is_a_new_revision_to_confirm(self):
        first = self.create()
        first = self.apply('confirm', first, review_hash=first['review']['review_hash'])
        self.assertEqual(first['status'], 'COMPLETED')
        # A site replaced by itself is no site change.
        self.followup = self.swap(device='device:sim-xx200', replaced='site:sim-b', new='site:sim-b')
        state = self.ask_again(first, '换 XX-200 呢')
        self.assertEqual(state['revision'], first['revision'] + 1)
        self.assertIn('用 XX-200 电台', state['request']['raw_text'])
        turn = state['conversation']['turns'][-1]
        self.assertEqual((turn['applied'], turn['mode'], turn['changes'][0]['before'], turn['changes'][0]['after']),
                         (True, 'llm', 'XX-100', 'XX-200'))
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')
        done = self.apply('confirm', state, review_hash=state['review']['review_hash'])
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertNotEqual(done['result'], first['result'])

    def test_a_site_swap_must_say_which_end(self):
        state = self.create()
        asked = self.ask_again(state, '换成 C 站呢')
        self.assertEqual(asked['request']['raw_text'], state['request']['raw_text'])
        self.assertIn('要把哪一端换成 C站？当前两端是 A站、B站', asked['conversation']['pending'][-1]['question'])
        # The model may repeat the radio already in use; that is no radio change.
        self.followup = self.swap(device='device:sim-xx100', replaced='site:sim-b', new='site:sim-c')
        swapped = self.ask_again(asked, 'B 站换成 C 站呢')
        self.assertIn('A 站到 C站用 XX-100', swapped['request']['raw_text'])
        self.assertEqual(swapped['conversation']['pending'], [])  # the clear swap answers the open question
        self.assertEqual(swapped['status'], 'AWAITING_CONFIRMATION', swapped['report']['questions'])

    def test_hedged_or_disputed_swaps_leave_the_task_unchanged(self):
        state = self.create()
        for message, answer in (('要不换 XX-200 呢', self.swap(device='device:sim-xx200')),
                                ('换 XX-200 呢', dict(action='clarify', new_device='', replaced_site='', new_site='')),
                                ('换 XX-200 呢', self.swap(device='device:sim-xx100'))):
            with self.subTest(message=message, answer=answer):
                self.followup = answer
                asked = self.ask_again(state, message)
                self.assertEqual(asked['request']['raw_text'], state['request']['raw_text'])
                self.assertFalse(asked['conversation']['turns'][-1]['applied'])
                state = asked
        # The model's different reading is kept for review and said in words on the turn.
        turn = state['conversation']['turns'][-1]
        self.assertEqual(turn['reading']['new_device'], 'device:sim-xx100')
        self.assertEqual(turn['diagnostics'], ['模型读作：换用 XX-100，与规则判断不一致，没有修改任务。'])
        # An open question keeps the task waiting for input: this version cannot be confirmed yet.
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        with self.assertRaisesRegex(ValueError, 'NOT_CONFIRMABLE'):
            self.apply('confirm', state, review_hash='')

    def test_a_radio_outside_the_library_is_usable_only_after_review(self):
        state = self.create()
        self.followup = self.swap(device='device:xx-300')
        asked = self.ask_again(state, '换 XX-300 呢')
        self.assertEqual(asked['request']['raw_text'], state['request']['raw_text'])
        self.assertIn('库里没有 XX-300 的记录', asked['conversation']['pending'][-1]['question'])
        chunk = next(c['id'] for c in DraftStore(self.root).chunks().values() if TABLE in c['description'])
        output = dict(found=True, names=['XX-300'], model='XX-300', tx_power_dbm=40, antenna_gain_dbi=6,
                      rx_sensitivity_dbm=-97, band_low_ghz=1.0, band_high_ghz=3.0,
                      evidence=[dict(field=f, chunk_id=chunk, quote=TABLE) for f in
                                ('names', 'model', 'tx_power_dbm', 'antenna_gain_dbi', 'rx_sensitivity_dbm', 'band_ghz')])
        draft = extract(self.root, 'device', [chunk], model(output))['draft']
        waiting = self.ask_again(asked, '换 XX-300 呢')
        self.assertEqual([p['number'] for p in waiting['conversation']['pending']], [2])  # the newer question replaces the older
        self.assertIn('只有未审核的草稿', waiting['conversation']['pending'][-1]['question'])
        DraftStore(self.root).review(draft['id'], '审核人', draft['content_hash'], 'approve')
        swapped = self.ask_again(waiting, '换 XX-300 呢')
        self.assertIn('用 XX-300 电台', swapped['request']['raw_text'])
        self.assertEqual(swapped['conversation']['pending'], [])
        self.assertEqual(swapped['status'], 'AWAITING_CONFIRMATION', swapped['report']['questions'])
        done = self.apply('confirm', swapped, review_hash=swapped['review']['review_hash'])
        self.assertEqual(done['status'], 'COMPLETED')
        power = next(p for p in done['report']['parameters_proposal'] if p['canonical_name'] == 'tx_power_dbm')
        self.assertEqual(power['origins'][0]['source_ref'], 'device:xx-300#tx_power_dbm')

    def test_other_messages_are_ordinary_supplements(self):
        state = self.create()
        changed = self.ask_again(state, '频率改为 2.4 GHz')
        self.assertNotIn('followup', changed['conversation']['turns'][-1])


if __name__ == '__main__':
    unittest.main()
